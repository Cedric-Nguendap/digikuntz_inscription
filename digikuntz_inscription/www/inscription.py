"""
/inscription            -> liste des formulaires ouverts
/inscription/<route>    -> formulaire (route déclarée dans hooks.website_route_rules)
"""

import frappe

from digikuntz_inscription.services.registration import get_form_fields, get_published_form


def get_context(context):
	context.no_cache = 1
	route = frappe.form_dict.get("route")

	if not route:
		context.forms = [
			f for f in frappe.get_all(
				"Formulaire Inscription", filters={"published": 1}, fields=["name", "title", "route", "amount", "currency"],
				order_by="modified desc",
			)
		]
		context.mode = "list"
		return context

	form = get_published_form(route)
	is_manager = "System Manager" in frappe.get_roles() or "Sales Manager" in frappe.get_roles()
	if not form or (not form.published and not is_manager):
		raise frappe.PageDoesNotExistError

	context.mode = "form"
	context.form = form
	context.preview = not form.published
	context.closed_reason = None if context.preview else form.get_closed_reason()
	context.fields = get_form_fields(form)
	context.formatted_amount = frappe.utils.fmt_money(form.amount, currency=form.currency)
	context.csrf_token = frappe.sessions.get_csrf_token() if frappe.session.user != "Guest" else ""
	context.title = form.title
	return context
