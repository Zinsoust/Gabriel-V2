# Démonstration Gabriel Prospect MVP 3 — 5 minutes

## Préconditions

- Flask tourne localement sur `http://127.0.0.1:5050` avec
  `AUTH_ENABLED=false`.
- Seul le stockage Gabriel Prospect pointe vers le projet Supabase DEV dédié.
- Supabase historique, Stripe, YouTube, Google et les fournisseurs IA sont
  désactivés.
- Le fichier de démonstration est
  `examples/gabriel_prospect_demo_5_agences.csv`.

## Parcours conseillé

### 0:00 — Ouvrir Gabriel Prospect

Ouvrir :
`http://127.0.0.1:5050/orchestrateur?agent=prospect`

Présenter le badge « Traitement local, sans IA » et rappeler que toutes les
données de la démonstration sont fictives (`.test` et `.invalid`).

### 0:45 — Montrer le pipeline sauvegardé

Ouvrir la section « Prospects sauvegardés ». Cinq agences doivent apparaître :

- trois au statut « Qualifié » ;
- une au statut « A répondu » ;
- une au statut « À enrichir ».

Utiliser la recherche et le filtre de statut pour montrer le rechargement
depuis PostgreSQL.

### 1:45 — Montrer le score et la provenance

Déplier une fiche. Montrer le score ICP, les critères, les déclarations
« Déclaré · non vérifié », les inconnues et l'absence d'hypothèse ajoutée au
score.

### 2:30 — Montrer l'historique commercial

Déplier la fiche au statut « A répondu ». L'historique doit montrer la création
puis les passages successifs par « Prêt à contacter », « Contacté » et
« A répondu ».

### 3:15 — Montrer la barrière `to_enrich`

Filtrer sur « À enrichir » et ouvrir la fiche concernée. Expliquer que son
canal professionnel est invalide ou absent et qu'une prise de contact est
refusée tant que la fiche n'est pas enrichie.

### 4:00 — Rejouer l'import sans duplication

Dans la section d'import, choisir
`examples/gabriel_prospect_demo_5_agences.csv`, puis « Analyser le CSV ».
Sélectionner les cinq lignes et demander l'enregistrement. Le résultat attendu
est `0 prospect enregistré · 5 doublons déjà sauvegardés` et le pipeline reste
à cinq fiches.

### 4:45 — Conclure sur les protections

Résumer les contrôles DEV déjà exécutés : isolation par utilisateur, historique
persisté, statut `do_not_contact` irréversible, empreinte conservée après
suppression, réimport et insertion directe bloqués par PostgreSQL.

Ne pas créer une nouvelle opposition pendant une démonstration ordinaire : son
empreinte est volontairement persistante. Ne pas ouvrir les autres agents ni
les écrans de paiement tant que leurs intégrations restent désactivées.
