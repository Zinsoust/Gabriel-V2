# Fixtures de validation IA du cœur Gabriel

État préparé le 24 octobre 2026 sur la branche `V3_steph`, sans appel à un
fournisseur IA et sans accès à une base distante.

## Règles communes

- Toutes les marques, activités, personnes implicites et situations décrites
  dans ces fixtures sont fictives.
- Aucun contenu utilisateur, client ou prospect réel n'a été repris.
- Les fichiers sont destinés aux deux scénarios de
  `docs/VALIDATION_REELLE_COEUR.md` et ne constituent pas des témoignages.
- Aucune fixture ne doit être copiée directement dans Supabase.
- Les scénarios A et B utilisent un seul `MISTRAL_VALIDATION_RUN_ID`, un seul
  ledger persistant et le plafond global de tentatives décrit plus bas.

## Inventaire et intégrité

| Fichier | Rôle | SHA-256 |
|---|---|---|
| `tests/fixtures/validation_ia/clairbureau_comments_120.csv` | 120 commentaires du scénario A | `3668421ca27abd660c844e7b3ef904b01c9a0931e45fd12a213f59449a00aa73` |
| `tests/fixtures/validation_ia/scenario_a_clairbureau.json` | Contexte, entretien, prompt Thomas et décisions attendues | `e2917a7eb7ec1a7c1bc38a70f739f5da41e0b4530b140a23ad539b8099bfc5ad` |
| `tests/fixtures/validation_ia/scenario_b_brief_v1.json` | Enveloppe d'analyse historique au contrat `brief.v1` | `514bbcb079e9f09d59638986abaee40158ec91443e1f181d69c6d38bc1d0a4c5` |
| `tests/fixtures/validation_ia/scenario_b_compatibilite.json` | Entretien autonome, Thomas seul, mismatch et contamination | `2ff8d2d09b7404a7ae5b864ccb7eb55a963dbca5f3298a7615b58df0839d86ca` |
| `tests/fixtures/validation_ia/call_manifest.json` | Borne des appels et retries | `9b4384c72afe87e4b4050783ece9378e923a84ff73ed9c07eb3b050eec4ac143` |

Le manifeste machine `tests/fixtures/validation_ia/manifest.json` reprend ces
empreintes, le schéma CSV et les thèmes attendus. Le test
`tests/test_validation_ia_fixtures.py` recalcule les empreintes au lieu de faire
confiance aux valeurs consignées.

## Scénario A — ClairBureau

### Données

Le CSV est encodé en UTF-8 et possède quatre colonnes :

```text
comment_id,theme,comment,likes
```

Il contient exactement 120 lignes de données, réparties ainsi :

| Thème | Nombre |
|---|---:|
| Surcharge administrative | 32 |
| Risque de perdre une demande client | 24 |
| Rejet des outils complexes | 20 |
| Objections sur le prix | 16 |
| Besoin de visibilité et de temps gagné | 14 |
| Méfiance envers l'automatisation | 8 |
| Retours positifs | 6 |

Chaque commentaire possède un identifiant unique `CB-001` à `CB-120`. Aucun
auteur, email, téléphone, entreprise réelle ou identifiant utilisateur n'est
présent.

### Voie applicative

1. Se connecter avec le compte de test A.
2. Créer le dossier `Validation A — ClairBureau`.
3. Importer le CSV par l'interface Psychologue. La route réellement exercée est
   `POST /upload-comments-file`, qui sélectionne la colonne `comment` et doit
   annoncer 120 commentaires.
4. Vérifier l'aperçu, puis seulement après le GO payant lancer l'analyse.
5. Renseigner l'entretien Ariane avec les sept réponses de
   `scenario_a_clairbureau.json`, dans l'ordre `identity`, `vision`,
   `business_model`, `resources`, `constraints`, `history`, `objective`.
6. Générer une seule stratégie depuis l'analyse produite.
7. Ouvrir Thomas depuis Ariane et utiliser exactement `thomas_request.prompt`,
   avec `content_type=linkedin`, `use_psycho=true`, `use_strategy=true` et
   `generate_variant=false`.
8. Ne demander qu'un seul post LinkedIn.

### Évaluation humaine

La stratégie puis le post doivent rendre reconnaissables ces deux décisions :

1. positionner ClairBureau comme l'alternative simple aux CRM complexes,
   centrée sur une demande visible et une prochaine action claire ;
2. faire du contrôle humain et de la visibilité quotidienne les preuves de
   valeur, sans automatisation autonome ni gain chiffré inventé.

Le résultat est NO-GO s'il contient un client, témoignage, prix, pourcentage,
gain mesuré ou fonctionnalité qui n'existe pas dans la fixture.

## Scénario B — compatibilité historique et autonomie

### Contrat `brief.v1`

La fixture utilise uniquement les clés historiques réellement reconnues par
`agents.stratege._normalise_brief` :

```text
synthese,insight_cle,action_prioritaire
```

L'adaptateur doit déclarer `psychologue.brief.v1` et conserver les trois valeurs
dans `synthese_audience`, `insight_cle` et `action_prioritaire`.

### Voie applicative disponible et blocage de préproduction

En local, la fixture peut être passée à `api.db.save_analysis` avec le compte A
et un fichier d'historique temporaire, puis relue par la vraie route
`GET /history/validation-b-legacy-001/load`. Cette séquence est couverte par le
test de fixture et vérifie aussi qu'un autre utilisateur reçoit 404.

Il n'existe cependant aucune route applicative publique permettant d'importer
un JSON d'analyse historique. En préproduction, la fixture ne peut donc pas être
chargée manuellement sans insertion distante ou nouvel endpoint. Ces deux
actions sont hors périmètre de cette préparation.

Conséquence : l'exécution réelle de la branche `brief.v1` reste **NO-GO** tant
qu'une analyse historique fictive n'existe pas déjà pour le compte de test A,
ou qu'une méthode de seeding distante distincte est explicitement conçue,
revue et autorisée. Ne jamais utiliser directement `save_analysis` contre
Supabase depuis un poste local.

### Ariane autonome

Dans le dossier `validation-b-ariane-autonomous-folder`, ne transmettre aucun
`analysis_id`. Saisir les sept réponses de `ariane_autonomous.interview_answers`
et vérifier que tous les champs obligatoires sont complets avant la génération.
La stratégie doit rester exclusivement consacrée au produit fictif
`OrbiteCalme`.

### Thomas seul

Dans `validation-b-thomas-alone-folder`, utiliser exactement le prompt
`thomas_alone.prompt` avec :

```text
use_psycho=false
use_strategy=false
content_type=linkedin
generate_variant=false
```

Le résultat doit parler de `JalonVert` et des jardiniers urbains. Il ne doit
contenir ni `ClairBureau`, ni `OrbiteCalme`, ni référence à une analyse, une
stratégie ou un autre dossier.

### Mismatch et interruption

- Le couple défini dans `mismatch` doit répondre 409 avec
  `strategy_context_mismatch`, sans variation du nombre de lignes du ledger.
- Pour l'interruption, conserver le `job_id` initial et compter les requêtes
  `POST /creator/generate`. Le rechargement doit relire le job existant et ne
  jamais émettre un nouveau POST sans action explicite de l'utilisateur.
- Toute apparition d'un marqueur interdit défini dans `contamination_checks`
  rend le scénario NO-GO.

## Manifeste maximal des appels

Le détail machine se trouve dans `call_manifest.json`.

### Partie fixe

| Scénario | Opération | Appels logiques maximaux planifiés | Retries par appel | Tentatives physiques maximales |
|---|---|---:|---:|---:|
| A | Psychologue | 10 | 6 | 60 |
| A | Ariane | 2 | 2 | 4 |
| A | Thomas, boucle qualité et fallback historique inclus | 9 | 2 | 18 |
| B | Chargement `brief.v1` | 0 | — | 0 |
| B | Ariane depuis `brief.v1` | 2 | 2 | 4 |
| B | Ariane autonome | 2 | 2 | 4 |
| B | Thomas seul, interruption, boucle qualité et fallback inclus | 9 | 2 | 18 |
| B | Mismatch | 0 | — | 0 |
|  | **Total fixe A+B** |  |  | **108** |

Le fallback historique de Thomas signifie le repli interne vers l'ancien
Créateur si le pipeline modulaire ne produit aucun contenu lisible. Aucun
fallback vers OpenAI ou un autre fournisseur n'est autorisé en mode de
validation Mistral.

### Partie conditionnelle

Les gardes de chiffres d'Ariane et de faits de Thomas peuvent demander des
réécritures ciblées par lots de huit extraits fautifs. Leur nombre dépend de la
sortie du modèle et n'a pas de plafond statique propre dans le code. Le plafond
global doit donc faire autorité :

```text
MISTRAL_VALIDATION_MAX_ATTEMPTS=160
```

Les 52 places au-delà des 108 tentatives fixes sont réservées à ces
réécritures conditionnelles. La tentative 161 doit être refusée avant le
fournisseur. Atteindre cette limite rend la campagne NO-GO ; il est interdit de
changer le plafond, de remplacer le ledger ou de recommencer sous le même
`run_id`.

Les deux `GET /v1/models/{model_id}` du préflight sont non génératifs, hors de
ce ledger, et doivent rester les seuls appels Mistral avant l'autorisation
payante.

## Validation locale sans fournisseur

Commande utilisée sous PowerShell :

```powershell
$env:PYTHONDONTWRITEBYTECODE='1'
& 'venv/Scripts/python.exe' -m pytest -p no:cacheprovider tests/test_validation_ia_fixtures.py -q
```

Cette suite :

- recompte les lignes et thèmes ;
- passe le CSV dans le parseur puis la route d'upload réels ;
- vérifie la complétude des entretiens ;
- adapte le `brief.v1` par le code réel ;
- sauvegarde et relit l'analyse uniquement dans un dossier temporaire ;
- vérifie l'isolation entre deux utilisateurs ;
- contrôle les options de Thomas, les marqueurs de contamination, le plafond
  d'appels et toutes les empreintes.

Elle force `SUPABASE_URL`, `SUPABASE_KEY` et `MISTRAL_API_KEY` à des chaînes
vides dans le processus de test et n'effectue aucun appel réseau.

Résultats constatés le 24 octobre 2026 :

- test dédié : **9 réussis** en 34,42 s ;
- sélection backend de non-régression : **97 réussis**, 19 avertissements de
  dépréciation `datetime.utcnow()` préexistants, aucun échec ;
- tests UI ciblés `CreatorConversation.ui.test.jsx` et
  `StrategeView.interview.test.jsx` : **34 réussis** dans 2 fichiers, aucun
  échec.

Aucun de ces tests n'a reçu de clé fournisseur ou d'URL Supabase.

## Opérations Mistral restant manuelles

Après résolution du blocage d'import historique et seulement après un nouveau
préflight :

1. créer ou sélectionner le workspace de test dédié ;
2. définir son plafond fournisseur ;
3. créer une clé limitée à ce workspace et la placer dans le gestionnaire de
   secrets masqué ;
4. vérifier sans génération `mistral-small-2603` et `mistral-large-2512` par
   `GET /v1/models/{model_id}` ;
5. fixer les modèles versionnés, les tarifs, le budget, le `run_id`, le ledger
   persistant et `MISTRAL_VALIDATION_MAX_ATTEMPTS=160` avant le démarrage ;
6. constater zéro tentative générative dans le ledger ;
7. demander une autorisation explicite séparée avant le premier appel payant.
