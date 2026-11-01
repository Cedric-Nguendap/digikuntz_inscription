"""Liens publics signés vers une inscription (page de statut, facture PDF)."""

import hashlib
import hmac
from contextlib import contextmanager
from urllib.parse import urlencode

import frappe
from frappe.utils import get_url
from frappe.utils.password import get_encryption_key


def sign(registration):
	secret = get_encryption_key().encode()
	return hmac.new(secret, f"digikuntz-inscription:{registration}".encode(), hashlib.sha256).hexdigest()[:32]


def validate(registration, key):
	if not (registration and key and hmac.compare_digest(sign(registration), str(key))):
		raise frappe.PermissionError("Lien invalide.")
	if not frappe.db.exists("Inscription", registration):
		raise frappe.PermissionError("Lien invalide.")


def status_url(registration):
	return get_url(f"/inscription-statut?{urlencode({'ins': registration, 'key': sign(registration)})}")


def invoice_url(registration):
	query = urlencode({"ins": registration, "key": sign(registration)})
	return get_url(f"/api/method/digikuntz_inscription.api.download_invoice?{query}")


@contextmanager
def as_administrator():
	"""Création client/facture/demande de paiement depuis la page publique (utilisateur Guest)."""
	user = frappe.session.user
	if user == "Administrator":
		yield
		return
	frappe.set_user("Administrator")
	try:
		yield
	finally:
		frappe.set_user(user)
