"""
Inscription publique : validation des réponses, puis création (dans une seule transaction)
de l'Inscription, du Client, de la Facture et de la Demande de paiement.

Le paiement lui-même est entièrement délégué à digikuntz_frappe_payment : on renvoie le
client vers `payment_request.payment_url`, et services/payment_hooks.py est appelé quand
le paiement est confirmé.
"""

import re

import frappe
from erpnext.accounts.doctype.payment_request.payment_request import make_payment_request
from frappe.utils import add_to_date, cint, flt, getdate, now_datetime, nowdate, validate_email_address

from digikuntz_inscription.digikuntz_inscription.doctype.formulaire_inscription.formulaire_inscription import (
	get_options,
)
from digikuntz_inscription.services.links import as_administrator

MAX_TEXT = {"Texte court": 140, "Texte long": 5000}
OPEN_PR_STATUSES = ("Requested", "Initiated", "Partially Paid")


class RegistrationError(frappe.ValidationError):
	def __init__(self, message, field_errors=None):
		super().__init__(message)
		self.field_errors = field_errors or {}


# ---------------------------------------------------------------------------- formulaire


def get_published_form(route):
	name = frappe.db.get_value("Formulaire Inscription", {"route": route}, "name") if route else None
	return frappe.get_doc("Formulaire Inscription", name) if name else None


def get_form_fields(form):
	"""Champs affichés, dans l'ordre : champs fixes puis champs configurés."""
	fields = [
		frappe._dict(fieldname="full_name", label="Nom complet", fieldtype="Texte court", reqd=1),
		frappe._dict(fieldname="email", label="Email", fieldtype="Email", reqd=1),
		frappe._dict(fieldname="phone", label="Téléphone", fieldtype="Téléphone", reqd=cint(form.phone_required),
		             placeholder="Ex : 237691234567"),
	]
	for row in form.form_fields:
		fields.append(frappe._dict(
			fieldname=row.fieldname, label=row.label, fieldtype=row.fieldtype, reqd=cint(row.reqd),
			placeholder=row.placeholder, description=row.description, options=get_options(row),
		))
	return fields


def validate_answers(form, data):
	"""Retourne {fieldname: valeur nettoyée} ou lève RegistrationError avec une erreur par champ."""
	values, errors = {}, {}
	for field in get_form_fields(form):
		raw = data.get(field.fieldname)
		raw = raw.strip() if isinstance(raw, str) else raw
		try:
			value = _clean_value(field, raw)
		except ValueError as e:
			errors[field.fieldname] = str(e)
			continue
		if field.reqd and field.fieldtype == "Case à cocher" and not value:
			errors[field.fieldname] = "Cette case doit être cochée."
			continue
		if field.reqd and value is None:
			errors[field.fieldname] = "Ce champ est obligatoire."
			continue
		values[field.fieldname] = value
	if errors:
		raise RegistrationError("Veuillez corriger les champs indiqués.", errors)
	return values


def _clean_value(field, raw):
	if raw in (None, ""):
		return 0 if field.fieldtype == "Case à cocher" else None
	t = field.fieldtype
	if t in MAX_TEXT:
		value = str(raw)
		if len(value) > MAX_TEXT[t]:
			raise ValueError(f"{MAX_TEXT[t]} caractères maximum.")
		return value
	if t == "Email":
		value = str(raw).lower()
		if not validate_email_address(value):
			raise ValueError("Adresse email invalide.")
		return value
	if t == "Téléphone":
		digits = re.sub(r"\D", "", str(raw))
		if not 8 <= len(digits) <= 15:
			raise ValueError("Numéro invalide : indiquez l'indicatif pays (ex : 237691234567).")
		return digits
	if t == "Nombre entier":
		if not re.fullmatch(r"-?\d+", str(raw)):
			raise ValueError("Nombre entier attendu.")
		return int(raw)
	if t == "Nombre décimal":
		try:
			return float(str(raw).replace(",", "."))
		except ValueError:
			raise ValueError("Nombre attendu.")
	if t == "Date":
		try:
			return str(getdate(raw))
		except Exception:
			raise ValueError("Date invalide.")
	if t == "Liste de choix":
		if raw not in field.options:
			raise ValueError("Choix invalide.")
		return raw
	if t == "Case à cocher":
		return 1 if str(raw).lower() in ("1", "true", "on", "oui", "yes") else 0
	raise ValueError("Type de champ inconnu.")


def format_value(field, value):
	if field.fieldtype == "Case à cocher":
		return "Oui" if value else "Non"
	if field.fieldtype == "Date" and value:
		return frappe.utils.formatdate(value)
	return "" if value is None else str(value)


# ----------------------------------------------------------------------------- inscription


def register(route, data, ip_address=None):
	"""Retourne {"registration": name, "payment_url": url}. Lève RegistrationError."""
	form = get_published_form(route)
	if not form:
		raise RegistrationError("Formulaire introuvable.")
	reason = form.get_closed_reason()
	if reason:
		raise RegistrationError(reason)

	values = validate_answers(form, data)
	email = values["email"]

	existing = _existing_registration(form, email)
	if existing:
		return existing

	registration = frappe.get_doc({
		"doctype": "Inscription",
		"formulaire": form.name,
		"status": "En attente de paiement",
		"full_name": values["full_name"],
		"email": email,
		"phone": values.get("phone"),
		"currency": form.currency,
		"ip_address": ip_address,
		"expires_at": add_to_date(now_datetime(), hours=cint(form.unpaid_expiry_hours) or 72),
		"responses": [
			{"fieldname": f.fieldname, "label": f.label, "value": format_value(f, values.get(f.fieldname))}
			for f in get_form_fields(form)
			if f.fieldname not in ("full_name", "email", "phone")
		],
	})
	registration.insert(ignore_permissions=True)

	with as_administrator():
		customer = _get_or_create_customer(form, registration)
		invoice = _create_sales_invoice(form, registration, customer)
		payment_request = _create_payment_request(form, registration, invoice)

	registration.update({
		"customer": customer,
		"sales_invoice": invoice.name,
		"amount": flt(invoice.rounded_total or invoice.grand_total),
		"payment_request": payment_request.name,
		"payment_url": payment_request.payment_url,
	})
	registration.save(ignore_permissions=True)
	return {"registration": registration.name, "payment_url": payment_request.payment_url}


def _existing_registration(form, email):
	"""Évite les doublons (double clic, retour arrière) et les réinscriptions si non autorisées."""
	rows = frappe.get_all(
		"Inscription",
		filters={"formulaire": form.name, "email": email, "status": ["in", ["Payée", "En attente de paiement"]]},
		fields=["name", "status", "payment_request", "payment_url"],
		order_by="creation desc",
	)
	for row in rows:
		if row.status == "Payée" and not form.allow_multiple:
			raise RegistrationError("Une inscription payée existe déjà avec cet email.", {"email": "Déjà inscrit."})
		if row.status == "En attente de paiement" and row.payment_request and (
			frappe.db.get_value("Payment Request", row.payment_request, "status") in OPEN_PR_STATUSES
		):
			# Reprendre le paiement en cours plutôt que créer une 2e facture
			return {"registration": row.name, "payment_url": row.payment_url, "resumed": True}
	return None


def _get_or_create_customer(form, registration):
	existing = frappe.db.get_value("Customer", {"email_id": registration.email, "disabled": 0}, "name")
	if existing:
		return existing
	customer = frappe.get_doc({
		"doctype": "Customer",
		"customer_name": registration.full_name,
		"customer_type": "Individual",
		"customer_group": form.customer_group
		or frappe.db.get_single_value("Selling Settings", "customer_group")
		or frappe.db.get_value("Customer Group", {"is_group": 0}, "name"),
		"territory": frappe.db.get_single_value("Selling Settings", "territory")
		or frappe.db.get_value("Territory", {"is_group": 0}, "name"),
		"email_id": registration.email,
		"mobile_no": registration.phone,
	})
	customer.insert(ignore_permissions=True)
	return customer.name


def _create_sales_invoice(form, registration, customer):
	invoice = frappe.new_doc("Sales Invoice")
	invoice.update({
		"company": form.company,
		"customer": customer,
		"currency": form.currency,
		"posting_date": nowdate(),
		"due_date": nowdate(),
		"ignore_pricing_rule": 1,
		"remarks": f"Inscription {registration.name} — {form.title}",
	})
	invoice.append("items", {
		"item_code": form.item,
		"qty": 1,
		"rate": flt(form.amount),
		"description": f"Inscription : {form.title} ({registration.full_name})",
	})
	invoice.set_missing_values()
	for item in invoice.items:
		item.rate = flt(form.amount)
	invoice.flags.ignore_permissions = True
	invoice.insert()
	invoice.submit()
	return invoice


def _create_payment_request(form, registration, invoice):
	args = {
		"dt": "Sales Invoice",
		"dn": invoice.name,
		"recipient_id": registration.email,
		"submit_doc": 1,
		"return_doc": 1,
		"mute_email": 1,
	}
	if form.payment_gateway_account:
		args["payment_gateway_account"] = form.payment_gateway_account
	payment_request = make_payment_request(**args)
	if payment_request.docstatus != 1 or not payment_request.payment_url:
		raise RegistrationError("Le paiement n'a pas pu être préparé (passerelle non configurée pour la société).")
	return payment_request
