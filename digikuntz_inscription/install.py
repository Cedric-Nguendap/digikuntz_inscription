import frappe


def before_install():
	if "digikuntz_frappe_payment" not in frappe.get_installed_apps():
		frappe.throw(
			"Installez d'abord digikuntz_frappe_payment : "
			"bench --site <site> install-app digikuntz_frappe_payment"
		)
