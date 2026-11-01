import json

import frappe
from frappe.rate_limiter import rate_limit

from digikuntz_inscription.services import links, registration as registration_service


@frappe.whitelist(allow_guest=True, methods=["POST"])
@rate_limit(limit=10, seconds=10 * 60)
def submit(route, data, website=None):
	"""Envoi du formulaire public. `website` est un champ piège invisible (anti-robots)."""
	if website:
		return {"ok": False, "error": "Requête refusée."}
	try:
		answers = json.loads(data) if isinstance(data, str) else (data or {})
	except ValueError:
		return {"ok": False, "error": "Données invalides."}

	# Tout ou rien : en cas d'erreur, aucune inscription / facture / demande de paiement orpheline
	frappe.db.savepoint("digikuntz_registration")
	try:
		result = registration_service.register(route, answers, ip_address=frappe.local.request_ip)
	except registration_service.RegistrationError as e:
		frappe.db.rollback(save_point="digikuntz_registration")
		frappe.clear_messages()
		return {"ok": False, "error": str(e), "errors": e.field_errors}
	except Exception:
		frappe.db.rollback(save_point="digikuntz_registration")
		frappe.clear_messages()
		frappe.log_error(title=f"Digikuntz Inscription : échec de l'inscription ({route})")
		return {"ok": False, "error": "L'inscription n'a pas pu être enregistrée. Veuillez réessayer plus tard."}
	return {"ok": True, **result}


@frappe.whitelist(allow_guest=True, methods=["GET", "POST"])
@rate_limit(limit=60, seconds=60)
def get_status(ins, key):
	"""Polling de la page /inscription-statut."""
	links.validate(ins, key)
	return get_status_summary(ins, refresh=True)


@frappe.whitelist(allow_guest=True, methods=["GET"])
@rate_limit(limit=20, seconds=60)
def download_invoice(ins, key):
	links.validate(ins, key)
	invoice = frappe.db.get_value("Inscription", ins, "sales_invoice")
	if not invoice:
		raise frappe.DoesNotExistError("Aucune facture pour cette inscription.")
	with links.as_administrator():
		pdf = frappe.get_print("Sales Invoice", invoice, as_pdf=True)
	frappe.local.response.filename = f"{invoice}.pdf"
	frappe.local.response.filecontent = pdf
	frappe.local.response.type = "pdf"


def get_status_summary(ins, refresh=False):
	from digikuntz_frappe_payment.services.extensions import get_payment_status

	reg = frappe.db.get_value(
		"Inscription", ins, ["status", "payment_request", "payment_url", "formulaire"], as_dict=True
	)
	payment_status = None
	if reg.status == "En attente de paiement" and reg.payment_request:
		payment_status = get_payment_status(reg.payment_request, refresh=refresh)
		if payment_status == "successful":
			reg.status = frappe.db.get_value("Inscription", ins, "status")
	pr_open = reg.payment_request and frappe.db.get_value("Payment Request", reg.payment_request, "status") in (
		registration_service.OPEN_PR_STATUSES
	)
	return {
		"status": reg.status,
		"payment_status": payment_status,
		"retry_url": reg.payment_url if reg.status == "En attente de paiement" and pr_open else None,
	}
