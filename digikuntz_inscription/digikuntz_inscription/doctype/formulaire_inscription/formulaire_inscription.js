frappe.ui.form.on("Formulaire Inscription", {
	setup(frm) {
		frm.set_query("payment_gateway_account", () => ({ filters: { company: frm.doc.company } }));
		frm.set_query("item", () => ({ filters: { is_sales_item: 1, disabled: 0 } }));
		frm.set_query("customer_group", () => ({ filters: { is_group: 0 } }));
	},

	refresh(frm) {
		if (frm.is_new()) return;
		const url = frm.doc.__onload && frm.doc.__onload.public_url;

		frm.add_custom_button(__("Ouvrir la page publique"), () => window.open(url, "_blank"));
		frm.add_custom_button(__("Copier le lien"), () => frappe.utils.copy_to_clipboard(url));
		frm.add_custom_button(__("Voir les inscriptions"), () =>
			frappe.set_route("List", "Inscription", { formulaire: frm.doc.name })
		);

		frm.dashboard.set_headline(
			frm.doc.published
				? `${__("Page publique")} : <a href="${url}" target="_blank">${frappe.utils.escape_html(url)}</a>`
				: __("Formulaire non publié : seuls les gestionnaires voient la page (aperçu).")
		);
		render_stats(frm);
	},

	company(frm) {
		frm.set_value("payment_gateway_account", "");
	},
});

frappe.ui.form.on("Champ Formulaire Inscription", {
	label(frm, cdt, cdn) {
		// Le nom technique est généré à l'enregistrement ; on le vide tant que la ligne est nouvelle
		const row = locals[cdt][cdn];
		if (row.__islocal) frappe.model.set_value(cdt, cdn, "fieldname", "");
	},
});

function render_stats(frm) {
	const stats = (frm.doc.__onload && frm.doc.__onload.stats) || {};
	const statuses = [
		["Payée", "green"],
		["En attente de paiement", "orange"],
		["Expirée", "gray"],
		["Annulée", "red"],
	];
	const cards = statuses
		.map(([status, color]) => {
			const s = stats[status] || { count: 0, total: 0 };
			const total = status === "Payée" ? `<div class="text-muted small">${format_currency(s.total, frm.doc.currency)}</div>` : "";
			return `<div class="col-sm-3" style="margin-bottom:10px">
				<a href="/app/inscription?formulaire=${encodeURIComponent(frm.doc.name)}&status=${encodeURIComponent(status)}"
				   style="display:block;border:1px solid var(--border-color);border-radius:8px;padding:12px;text-decoration:none">
					<span class="indicator-pill ${color}">${__(status)}</span>
					<div style="font-size:22px;font-weight:700;margin-top:6px">${s.count}</div>${total}
				</a></div>`;
		})
		.join("");
	frm.get_field("stats_html").$wrapper.html(`<div class="row">${cards}</div>`);
}
