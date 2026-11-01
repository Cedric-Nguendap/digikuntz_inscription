"""
Scénario complet inscription -> facture -> paiement -> confirmation, sur un vrai site.
Passerelles simulées (aucun appel réel), TOUT est annulé à la fin.

    bench --site <site> execute digikuntz_inscription.tests.e2e_check.run \
        --kwargs "{'company': 'Digikunktz', 'item': 'Service-Infos'}"
"""

import json
import os
import traceback
from unittest import mock

import frappe
from frappe.utils import add_to_date, now_datetime

from digikuntz_frappe_payment.tests.e2e_check import FakeGateways


def _render(template, context):
	path = os.path.join(frappe.get_app_path("digikuntz_inscription", "www"), template)
	with open(path, encoding="utf-8") as fh:
		return frappe.render_template(fh.read(), dict(context))


def run(company=None, item=None):
	results = []

	def check(label, condition, detail=""):
		results.append({"ok": bool(condition), "test": label, "detail": str(detail)[:400]})

	try:
		_scenarios(company, item, check)
	except Exception:
		results.append({"ok": False, "test": "EXCEPTION", "detail": traceback.format_exc()[-3000:]})
	finally:
		frappe.db.rollback()
		frappe.set_user("Administrator")
		frappe.clear_cache()

	passed = sum(r["ok"] for r in results)
	print(f"\n===== Digikuntz Inscription e2e : {passed}/{len(results)} OK (transaction annulée) =====")
	for r in results:
		print(("  OK  " if r["ok"] else "  KO  ") + r["test"] + (f"  -> {r['detail']}" if not r["ok"] and r["detail"] else ""))


def _scenarios(company, item, check):
	from digikuntz_frappe_payment.api import payment as payment_api
	from digikuntz_frappe_payment.services.extensions import get_return_url
	from digikuntz_frappe_payment.services.webhook_service import handle_webhook

	from digikuntz_inscription import api
	from digikuntz_inscription.services import cleanup, links
	from digikuntz_inscription.www import inscription as form_page
	from digikuntz_inscription.www import inscription_statut as status_page

	frappe.set_user("Administrator")
	company = company or frappe.db.get_value("Company", {"custom_payment_gateway": ["is", "set"]}, "name")
	item = item or frappe.db.get_value("Item", {"is_sales_item": 1, "disabled": 0, "is_stock_item": 0}, "name")
	pga = frappe.db.get_value("Payment Gateway Account", {"company": company, "payment_gateway": "PawaPay Gateway"}, "name")

	# ----------------------------------------------------------- 1. configuration
	form = frappe.get_doc({
		"doctype": "Formulaire Inscription",
		"title": "Séminaire Test É2E",
		"published": 1,
		"company": company,
		"item": item,
		"amount": 25,
		"payment_gateway_account": pga,
		"phone_required": 1,
		"introduction": "<p>Inscription au séminaire.</p>",
		"form_fields": [
			{"label": "Établissement", "fieldtype": "Texte court", "reqd": 1},
			{"label": "Niveau d'études", "fieldtype": "Liste de choix", "options": "Licence\nMaster\nDoctorat", "reqd": 1},
			{"label": "Date de naissance", "fieldtype": "Date"},
			{"label": "J'accepte le règlement", "fieldtype": "Case à cocher", "reqd": 1},
			{"label": "Email", "fieldtype": "Texte court"},
		],
	}).insert()
	fieldnames = [r.fieldname for r in form.form_fields]
	check("1. route générée depuis le titre (sans accents)", form.route == "seminaire-test-e2e", form.route)
	check("1. noms techniques générés, réservés évités",
	      fieldnames == ["etablissement", "niveau_d_etudes", "date_de_naissance", "j_accepte_le_reglement", "champ_email"], fieldnames)

	frappe.set_user("Guest")  # (set_user réinitialise form_dict : à faire avant)
	frappe.local.form_dict = frappe._dict(route=form.route)
	ctx = form_page.get_context(frappe._dict())
	check("1. page publique : champs fixes + champs configurés",
	      [f.fieldname for f in ctx.fields][:3] == ["full_name", "email", "phone"] and len(ctx.fields) == 8 and not ctx.closed_reason)
	html = _render("inscription.html", ctx)
	check("1. rendu HTML du formulaire (types de champs)",
	      all(s in html for s in ('name="etablissement"', '<option value="Master">', 'type="date"', 'type="checkbox"',
	                              'type="email"', 'type="tel"', "Inscription au séminaire", 'name="website"')), html[:300])
	frappe.local.form_dict = frappe._dict()
	html = _render("inscription.html", form_page.get_context(frappe._dict()))
	check("1. rendu HTML de la liste des formulaires ouverts", f'href="/inscription/{form.route}"' in html)

	# --------------------------------------------------------- 2. validation
	bad = api.submit(form.route, json.dumps({"full_name": "A", "email": "pas-un-email", "phone": "12",
	                                          "niveau_d_etudes": "Bac+12"}))
	check("2. validation : une erreur par champ invalide",
	      not bad["ok"] and set(bad["errors"]) == {"email", "phone", "etablissement", "niveau_d_etudes", "j_accepte_le_reglement"},
	      bad)
	check("2. champ piège rempli (robot) -> refusé", not api.submit(form.route, "{}", website="http://spam")["ok"])
	check("2. aucune inscription créée par une soumission invalide",
	      not frappe.db.exists("Inscription", {"formulaire": form.name}))

	# --------------------------------------------- 3. inscription valide (Guest)
	answers = {
		"full_name": "Awa Test", "email": "Awa.Test.E2E@example.com", "phone": "237690000001",
		"etablissement": "Université de Douala", "niveau_d_etudes": "Master",
		"date_de_naissance": "2000-05-17", "j_accepte_le_reglement": 1,
	}
	res = api.submit(form.route, json.dumps(answers))
	check("3. inscription acceptée -> lien de paiement signé", res.get("ok") and "/pay?pr=" in (res.get("payment_url") or ""), res)
	frappe.set_user("Administrator")
	reg = frappe.get_doc("Inscription", res.get("registration"))
	inv = frappe.get_doc("Sales Invoice", reg.sales_invoice)
	pr = frappe.get_doc("Payment Request", reg.payment_request)
	check("3. inscription en attente, email normalisé", reg.status == "En attente de paiement" and reg.email == "awa.test.e2e@example.com")
	check("3. client créé", reg.customer and frappe.db.get_value("Customer", reg.customer, "email_id") == reg.email, reg.customer)
	check("3. facture soumise au bon montant", inv.docstatus == 1 and inv.grand_total == 25 and inv.items[0].item_code == item,
	      (inv.docstatus, inv.grand_total))
	check("3. demande de paiement PawaPay soumise", pr.docstatus == 1 and pr.payment_gateway == "PawaPay Gateway", pr.payment_gateway)
	check("3. réponses enregistrées et lisibles",
	      {r.label: r.value for r in reg.responses} == {
	          "Établissement": "Université de Douala", "Niveau d'études": "Master",
	          "Date de naissance": frappe.utils.formatdate("2000-05-17"), "J'accepte le règlement": "Oui", "Email": "",
	      }, [(r.label, r.value) for r in reg.responses])

	frappe.set_user("Guest")
	again = api.submit(form.route, json.dumps(answers))
	frappe.set_user("Administrator")
	check("3. double soumission -> reprise du même paiement, pas de 2e facture",
	      again.get("registration") == reg.name and again.get("resumed")
	      and frappe.db.count("Sales Invoice", {"customer": reg.customer, "docstatus": 1}) == 1, again)

	# ------------------------------------------------------------ 4. paiement
	fake = FakeGateways()
	with mock.patch("digikuntz_frappe_payment.integrations.base_client.requests.request", side_effect=fake):
		push = payment_api.initiate_momo_push(pr.name, "690000001", "MTN_MOMO_CMR")
		check("4. push Mobile Money initié via le module de paiement", push.get("ok"), push)
		deposit = frappe.db.get_value("Payment Attempt", push.get("attempt"), "transaction_id")

		frappe.set_user("Guest")
		status = api.get_status(reg.name, links.sign(reg.name))
		check("4. page de statut : paiement en cours", status["status"] == "En attente de paiement" and status["payment_status"] == "pending", status)

		fake.pp[deposit] = {"status": "COMPLETED", "amount": "25.00", "currency": inv.currency}
		handle_webhook(json.dumps({"depositId": deposit, "status": "COMPLETED"}), {})
		frappe.set_user("Administrator")

	reg.reload()
	check("4. inscription Payée avec date, passerelle et écriture",
	      reg.status == "Payée" and reg.paid_on and reg.payment_entry and reg.payment_gateway == "PawaPay",
	      (reg.status, reg.paid_on, reg.payment_entry))
	check("4. facture soldée", frappe.db.get_value("Sales Invoice", inv.name, "outstanding_amount") == 0)
	check("4. email de confirmation mis en file",
	      frappe.db.exists("Email Queue", {"reference_doctype": "Inscription", "reference_name": reg.name}))
	check("4. retour de paiement -> page de statut de l'inscription",
	      "/inscription-statut?ins=" in (get_return_url(pr.name, "successful") or ""))

	frappe.set_user("Guest")
	frappe.local.form_dict = frappe._dict(ins=reg.name, key=links.sign(reg.name))
	ctx = status_page.get_context(frappe._dict())
	check("4. page de statut publique : confirmée + lien facture", ctx.valid and ctx.status == "Payée" and "download_invoice" in ctx.invoice_url)
	frappe.local.form_dict = frappe._dict(ins=reg.name, key="mauvaise-cle")
	check("4. page de statut : clé invalide refusée", not status_page.get_context(frappe._dict()).valid)
	html = _render("inscription-statut.html", ctx)
	check("4. rendu HTML de la page de statut (payée)",
	      "Inscription confirmée" in html and reg.name in html and "Télécharger la facture" in html)
	# Le PDF dépend de wkhtmltopdf et du serveur web (feuilles de style) : non testé ici,
	# seule la protection par clé l'est.
	try:
		api.download_invoice(reg.name, "mauvaise-cle")
		check("4. facture PDF : clé invalide refusée", False)
	except frappe.PermissionError:
		check("4. facture PDF : clé invalide refusée", True)
	frappe.set_user("Administrator")

	# ------------------------------------------- 5. règles d'inscription
	frappe.set_user("Guest")
	dup = api.submit(form.route, json.dumps(answers))
	check("5. déjà inscrit (payé) avec cet email -> refusé", not dup["ok"] and "email" in dup.get("errors", {}), dup)

	other = dict(answers, email="autre.e2e@example.com", full_name="Paul Test")
	res2 = api.submit(form.route, json.dumps(other))
	frappe.set_user("Administrator")
	reg2 = res2.get("registration")
	check("5. deuxième participant inscrit", res2.get("ok"), res2)

	# ------------------------------------------------- 6. expiration non payée
	frappe.db.set_value("Inscription", reg2, "expires_at", add_to_date(now_datetime(), hours=-1))
	with mock.patch("digikuntz_frappe_payment.integrations.base_client.requests.request", side_effect=FakeGateways()):
		cleanup.expire_unpaid_registrations(commit=False)
	reg2_doc = frappe.get_doc("Inscription", reg2)
	check("6. non payée après délai -> Expirée", reg2_doc.status == "Expirée", reg2_doc.status)
	check("6. facture et demande de paiement annulées",
	      frappe.db.get_value("Sales Invoice", reg2_doc.sales_invoice, "docstatus") == 2
	      and frappe.db.get_value("Payment Request", reg2_doc.payment_request, "docstatus") == 2)

	# ------------------------------------------------- 7. fermeture du formulaire
	form.reload()
	form.max_registrations = 1
	form.save()
	check("7. nombre max d'inscrits payés atteint -> fermé", form.get_closed_reason() == "Toutes les places ont été attribuées.")
	form.max_registrations = 0
	form.published = 0
	form.save()
	frappe.set_user("Guest")
	closed = api.submit(form.route, json.dumps(dict(answers, email="trois.e2e@example.com")))
	check("7. formulaire non publié -> inscription refusée", not closed["ok"], closed)
	frappe.local.form_dict = frappe._dict(route=form.route)
	try:
		form_page.get_context(frappe._dict())
		check("7. formulaire non publié invisible pour un visiteur", False)
	except frappe.PageDoesNotExistError:
		check("7. formulaire non publié invisible pour un visiteur", True)

	# ------------------------------------------------------- 8. permissions
	check("8. un visiteur ne peut pas lire les inscriptions", not frappe.has_permission("Inscription", "read"))
	frappe.set_user("Administrator")
	check("8. statistiques du formulaire",
	      form.get_stats().get("Payée", {}).get("count") == 1 and form.get_stats().get("Expirée", {}).get("count") == 1,
	      form.get_stats())
