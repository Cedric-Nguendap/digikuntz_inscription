app_name = "digikuntz_inscription"
app_title = "Digikuntz Inscription"
app_publisher = "Digikuntz"
app_description = "Plateforme d'inscription avec paiement"
app_email = "cednguendap@gmail.com"
app_license = "mit"

# digikuntz_frappe_payment est aussi requis, mais n'est pas listé ici : Frappe résoudrait
# le nom comme un dépôt GitHub public. La présence est vérifiée dans before_install.
required_apps = ["erpnext"]
before_install = "digikuntz_inscription.install.before_install"

# Pages publiques : /inscription/<route du formulaire>
website_route_rules = [
	{"from_route": "/inscription/<route>", "to_route": "inscription"},
]

# Points d'extension du module digikuntz_frappe_payment
digikuntz_on_payment_success = ["digikuntz_inscription.services.payment_hooks.on_payment_success"]
digikuntz_payment_return_url = ["digikuntz_inscription.services.payment_hooks.get_return_url"]

doc_events = {
	"Payment Request": {
		"on_cancel": "digikuntz_inscription.services.payment_hooks.on_payment_request_cancel",
	},
}

scheduler_events = {
	"hourly": [
		"digikuntz_inscription.services.cleanup.expire_unpaid_registrations",
	],
}
