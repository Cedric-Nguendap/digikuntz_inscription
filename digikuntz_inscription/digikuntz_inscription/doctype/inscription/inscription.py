from frappe.model.document import Document

from digikuntz_inscription.services import links


class Inscription(Document):
	"""Créée par la page publique (services/registration.py), mise à jour par le module de paiement."""

	def onload(self):
		self.set_onload("status_url", links.status_url(self.name))
