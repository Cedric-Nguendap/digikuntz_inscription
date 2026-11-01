import frappe
from frappe.utils import now_datetime

from digikuntz_inscription.services.links import as_administrator


def expire_unpaid_registrations(commit=True):
	"""
	Tâche horaire : les inscriptions non payées après le délai du formulaire expirent,
	et leur demande de paiement + facture sont annulées (aucune créance fantôme).
	Le statut est re-vérifié auprès de la passerelle juste avant, au cas où le client vient de payer.
	"""
	from digikuntz_frappe_payment.services.extensions import get_payment_status

	names = frappe.get_all(
		"Inscription",
		filters={"status": "En attente de paiement", "expires_at": ["<", now_datetime()]},
		pluck="name",
		limit=200,
	)
	for name in names:
		try:
			registration = frappe.get_doc("Inscription", name)
			if registration.payment_request and get_payment_status(registration.payment_request, refresh=True) in (
				"successful", "pending",
			):
				# Payé (le hook met à jour l'inscription) ou paiement en cours de validation : on attend
				if commit:
					frappe.db.commit()
				continue
			with as_administrator():
				_cancel_documents(registration)
			frappe.db.set_value("Inscription", name, {
				"status": "Expirée",
				"error": "Non payée dans le délai : facture et demande de paiement annulées.",
			})
			if commit:
				frappe.db.commit()
		except Exception:
			if commit:
				frappe.db.rollback()
			frappe.log_error(title=f"Digikuntz Inscription : expiration {name}")
			if commit:
				frappe.db.commit()
	return names


def _cancel_documents(registration):
	if registration.payment_request:
		pr = frappe.get_doc("Payment Request", registration.payment_request)
		if pr.docstatus == 1 and pr.status not in ("Paid", "Cancelled"):
			pr.flags.ignore_permissions = True
			pr.cancel()
	if registration.sales_invoice:
		invoice = frappe.get_doc("Sales Invoice", registration.sales_invoice)
		if invoice.docstatus == 1 and abs(invoice.outstanding_amount - invoice.grand_total) < 0.01:
			invoice.flags.ignore_permissions = True
			invoice.flags.ignore_links = True
			invoice.cancel()
