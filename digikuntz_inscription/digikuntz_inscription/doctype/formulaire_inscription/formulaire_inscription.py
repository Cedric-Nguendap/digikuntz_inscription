import re
import unicodedata

import frappe
from frappe.model.document import Document
from frappe.utils import cint, flt, get_url, getdate, nowdate

#: Champs toujours présents (colonnes du DocType Inscription) : interdits comme champs supplémentaires
CORE_FIELDNAMES = {"full_name", "email", "phone"}
RESERVED_FIELDNAMES = CORE_FIELDNAMES | {"name", "doctype", "route", "key", "website", "data"}


def slugify(text, separator="-"):
	text = unicodedata.normalize("NFKD", str(text or "")).encode("ascii", "ignore").decode()
	return re.sub(r"[^a-z0-9]+", separator, text.lower()).strip(separator)


class FormulaireInscription(Document):
	def validate(self):
		self.route = slugify(self.route or self.title)
		if not self.route:
			frappe.throw("L'adresse de la page est invalide.")
		if flt(self.amount) <= 0:
			frappe.throw("Le montant de l'inscription doit être supérieur à 0.")
		if cint(self.unpaid_expiry_hours) < 1:
			self.unpaid_expiry_hours = 72
		if not frappe.db.get_value("Item", self.item, "is_sales_item"):
			frappe.throw(f"L'article {self.item} doit être un article de vente.")
		if self.payment_gateway_account and (
			frappe.db.get_value("Payment Gateway Account", self.payment_gateway_account, "company") != self.company
		):
			frappe.throw("Le compte de passerelle doit appartenir à la société du formulaire.")
		self._validate_form_fields()

	def _validate_form_fields(self):
		used = set()
		for row in self.form_fields:
			if not row.fieldname:
				base = slugify(row.label, "_")[:50] or f"champ_{row.idx}"
				if base in RESERVED_FIELDNAMES or base[0].isdigit():
					base = f"champ_{base}"
				fieldname, n = base, 2
				while fieldname in used:
					fieldname, n = f"{base}_{n}", n + 1
				row.fieldname = fieldname
			if row.fieldname in used:
				frappe.throw(f"Ligne {row.idx} : le champ « {row.label} » est en double.")
			used.add(row.fieldname)
			if row.fieldtype == "Liste de choix" and not get_options(row):
				frappe.throw(f"Ligne {row.idx} : indiquez les choix possibles pour « {row.label} ».")

	def onload(self):
		self.set_onload("public_url", self.public_url)
		self.set_onload("stats", self.get_stats())

	@property
	def public_url(self):
		return get_url(f"/inscription/{self.route}")

	def get_stats(self):
		rows = frappe.db.sql(
			"""select status, count(*) as count, sum(amount) as total
			from `tabInscription` where formulaire = %s group by status""",
			self.name,
			as_dict=True,
		)
		return {r.status: {"count": r.count, "total": flt(r.total)} for r in rows}

	def get_closed_reason(self):
		"""None si les inscriptions sont ouvertes, sinon le message à afficher."""
		if not self.published:
			return "Les inscriptions ne sont pas ouvertes."
		if self.closing_date and getdate(nowdate()) > getdate(self.closing_date):
			return "Les inscriptions sont closes."
		if cint(self.max_registrations) and frappe.db.count(
			"Inscription", {"formulaire": self.name, "status": "Payée"}
		) >= cint(self.max_registrations):
			return "Toutes les places ont été attribuées."
		return None


def get_options(row):
	return [o.strip() for o in (row.options or "").split("\n") if o.strip()]
