frappe.listview_settings["Inscription"] = {
	add_fields: ["status", "paid_on", "sales_invoice"],
	has_indicator_for_draft: true,
	get_indicator(doc) {
		const colors = { "Payée": "green", "En attente de paiement": "orange", "Expirée": "gray", "Annulée": "red" };
		return [__(doc.status), colors[doc.status] || "blue", `status,=,${doc.status}`];
	},
	onload(listview) {
		listview.page.add_inner_button(__("Formulaires"), () => frappe.set_route("List", "Formulaire Inscription"));
	},
};
