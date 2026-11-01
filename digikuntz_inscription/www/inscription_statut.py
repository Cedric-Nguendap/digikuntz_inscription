"""/inscription-statut?ins=<Inscription>&key=<signature> — résultat de l'inscription après le paiement."""

import frappe

from digikuntz_inscription.api import get_status_summary
from digikuntz_inscription.services import links


def get_context(context):
	context.no_cache = 1
	context.valid = False
	ins, key = frappe.form_dict.get("ins"), frappe.form_dict.get("key")
	try:
		links.validate(ins, key)
	except frappe.PermissionError:
		return context

	summary = get_status_summary(ins, refresh=True)
	registration = frappe.db.get_value(
		"Inscription", ins, ["name", "full_name", "email", "formulaire", "amount", "currency", "paid_on"], as_dict=True
	)
	form = frappe.db.get_value("Formulaire Inscription", registration.formulaire, ["title", "route", "success_message"], as_dict=True)

	context.update({
		"valid": True,
		"ins": ins,
		"key": key,
		"registration": registration,
		"form": form,
		"status": summary["status"],
		"payment_status": summary["payment_status"],
		"retry_url": summary["retry_url"],
		"invoice_url": links.invoice_url(ins),
		"formatted_amount": frappe.utils.fmt_money(registration.amount, currency=registration.currency),
	})
	return context
