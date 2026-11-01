### Digikuntz Inscription

Formulaires d'inscription publics **configurables sans code**, avec paiement en ligne via
[digikuntz_frappe_payment](../digikuntz_frappe_payment) (Flutterwave, PawaPay).

### Installation

```bash
bench --site <site> install-app digikuntz_frappe_payment   # prérequis
bench --site <site> install-app digikuntz_inscription
```

### Utilisation

1. **Inscriptions → Formulaires → Nouveau**
   - *Titre*, *Société*, *Article facturé* (un service), *Montant*.
   - *Champs supplémentaires* : libellé, type, obligatoire. Nom complet et Email sont toujours demandés,
     le Téléphone est optionnel ou obligatoire.
     Types : Texte court, Texte long, Email, Téléphone, Nombre entier, Nombre décimal, Date, Liste de choix
     (un choix par ligne), Case à cocher (ex. « J'accepte le règlement », obligatoire = doit être cochée).
   - Options : date de clôture, nombre maximum d'inscrits payés, délai de paiement, inscriptions multiples
     avec le même email, passerelle (sinon celle par défaut de la société), email de confirmation.
   - Cocher **Publié**. Avant publication, les gestionnaires voient la page en aperçu.
2. Partager le lien : `https://<site>/inscription/<adresse>` (bouton « Copier le lien »).
   `https://<site>/inscription` liste les formulaires ouverts.
3. Suivre les inscriptions : **Inscriptions** (Workspace) ou la liste *Inscription*.
   Les filtres par formulaire et par statut sont disponibles, et le formulaire affiche ses statistiques.

### Parcours du participant

```
/inscription/<adresse>  formulaire  ──►  Inscription (En attente de paiement)
                                          + Client + Facture (soumise) + Demande de paiement
                        ──► page de paiement (web ou Mobile Money, module digikuntz_frappe_payment)
paiement confirmé (webhook / vérification automatique / retour du client)
                        ──► Inscription « Payée » : date, passerelle, écriture de paiement, email de confirmation
                        ──► /inscription-statut : confirmation + facture PDF
non payée après le délai ──► « Expirée », facture et demande de paiement annulées automatiquement
```

Chaque inscription donne accès, depuis le desk, à sa facture (et son PDF), à sa demande de paiement, à son
écriture de paiement et à la page de statut vue par le participant.

### Sécurité

- Pages de statut et factures accessibles uniquement par lien signé (`key=`).
- Limitation de débit sur l'envoi du formulaire, champ piège anti-robots, validation de chaque champ côté serveur.
- Double envoi / retour arrière : la même inscription et le même paiement sont repris (pas de facture en double).
- Le statut « Payée » n'est posé que sur confirmation du module de paiement (vérification API), jamais par la page de retour.

### Tests

```bash
bench --site <site> execute digikuntz_inscription.tests.e2e_check.run \
      --kwargs "{'company': '<Société>', 'item': '<Article de service>'}"
```

Passerelles simulées, transaction annulée à la fin.

### Prérequis

- Génération des factures PDF : `wkhtmltopdf` **0.12.6 avec Qt patché** (paquet de
  [wkhtmltopdf.org](https://wkhtmltopdf.org/downloads.html), pas celui des dépôts Ubuntu).
- Emails de confirmation : un compte email sortant configuré.

### License

mit

## Author

Cédric Nguendap (cednguendap@gmail.com)
