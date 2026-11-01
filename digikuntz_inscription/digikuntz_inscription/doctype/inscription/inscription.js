frappe.ui.form.on("Inscription", {
	refresh(frm) {
		const status_url = frm.doc.__onload && frm.doc.__onload.status_url;

		if (frm.doc.sales_invoice) {
			frm.add_custom_button(__("Facture (PDF)"), () => {
				const params = new URLSearchParams({ doctype: "Sales Invoice", name: frm.doc.sales_invoice });
				window.open(`/api/method/frappe.utils.print_format.download_pdf?${params}`, "_blank");
			}, __("Documents"));
			frm.add_custom_button(__("Facture"), () => frappe.set_route("Form", "Sales Invoice", frm.doc.sales_invoice), __("Documents"));
		}
		if (frm.doc.payment_request) {
			frm.add_custom_button(__("Demande de paiement"), () => frappe.set_route("Form", "Payment Request", frm.doc.payment_request), __("Documents"));
		}
		if (frm.doc.payment_entry) {
			frm.add_custom_button(__("Écriture de paiement"), () => frappe.set_route("Form", "Payment Entry", frm.doc.payment_entry), __("Documents"));
		}

		if (frm.doc.status === "En attente de paiement" && frm.doc.payment_request) {
			frm.add_custom_button(__("Vérifier le paiement"), () => {
				frappe.call({
					method: "digikuntz_frappe_payment.api.payment.refresh_payment_status",
					args: { payment_request_name: frm.doc.payment_request },
					freeze: true,
					freeze_message: __("Vérification auprès de la passerelle…"),
				}).then(() => frm.reload_doc());
			});
			if (frm.doc.payment_url) {
				frm.add_custom_button(__("Copier le lien de paiement"), () => frappe.utils.copy_to_clipboard(frm.doc.payment_url));
			}
		}
		if (status_url) {
			frm.add_custom_button(__("Page du participant"), () => window.open(status_url, "_blank"));
		}

		const colors = { "Payée": "green", "En attente de paiement": "orange", "Expirée": "gray", "Annulée": "red" };
		frm.page.set_indicator(__(frm.doc.status), colors[frm.doc.status] || "blue");
	},
});
