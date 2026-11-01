"""
Branchement sur les points d'extension de digikuntz_frappe_payment (voir hooks.py).
"""

import frappe
from frappe.utils import now_datetime

from digikuntz_inscription.services import links


def _registration_for(payment_request):
	if payment_request.reference_doctype != "Sales Invoice":
		return None
	return frappe.db.get_value("Inscription", {"payment_request": payment_request.name}, "name") or frappe.db.get_value(
		"Inscription", {"sales_invoice": payment_request.reference_name}, "name"
	)


def on_payment_success(payment_request, attempt):
	"""Paiement confirmé (Payment Entry créée). Idempotent : peut être relancé par le module de paiement."""
	name = _registration_for(payment_request)
	if not name:
		return
	registration = frappe.get_doc("Inscription", name)
	if registration.status == "Payée":
		return

	registration.update({
		"status": "Payée",
		"paid_on": attempt.completed_at or now_datetime(),
		"payment_entry": attempt.payment_entry,
		"payment_gateway": attempt.gateway,
		"payment_request": payment_request.name,
		"error": None,
	})
	registration.save(ignore_permissions=True)
	_send_confirmation(registration)


def get_return_url(payment_request, status):
	"""Fin du paiement : le client revient sur la page de statut de son inscription."""
	name = _registration_for(payment_request)
	return links.status_url(name) if name else None


def on_payment_request_cancel(doc, method=None):
	"""Demande de paiement annulée à la main : l'inscription en attente est annulée."""
	name = frappe.db.get_value(
		"Inscription", {"payment_request": doc.name, "status": "En attente de paiement"}, "name"
	)
	if name:
		frappe.db.set_value("Inscription", name, {
			"status": "Annulée",
			"error": f"Demande de paiement {doc.name} annulée.",
		})


def _send_confirmation(registration):
	form = frappe.get_cached_doc("Formulaire Inscription", registration.formulaire)
	if not form.send_confirmation_email or not registration.email:
		return
	context = {"doc": registration, "form": form}
	message = frappe.render_template(form.confirmation_message or "", context)
	message += (
		f'<p><a href="{links.status_url(registration.name)}">Voir mon inscription</a> · '
		f'<a href="{links.invoice_url(registration.name)}">Télécharger la facture</a></p>'
	)
	frappe.sendmail(
		recipients=[registration.email],
		subject=frappe.render_template(form.confirmation_subject or "Confirmation d'inscription", context),
		message=message,
		reference_doctype="Inscription",
		reference_name=registration.name,
	)
