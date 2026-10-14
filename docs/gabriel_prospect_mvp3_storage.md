# Gabriel Prospect MVP 3 — stockage DEV

## Configuration serveur

Le stockage Prospect utilise exclusivement :

- `GABRIEL_PROSPECT_SUPABASE_URL` ;
- `GABRIEL_PROSPECT_SUPABASE_SECRET_KEY`.

Ces variables restent côté Flask. L'absence d'une valeur, une configuration
partielle ou un échec de création du client désactive la persistance Prospect :
les routes de stockage répondent alors `prospect_storage_unavailable` (HTTP
503). Il n'existe aucun fallback vers `SUPABASE_URL` ou `SUPABASE_KEY`.
La prévisualisation CSV reste utilisable sans Supabase.

En développement Windows, elles peuvent être renseignées une seule fois dans
`.env.prospect.local`, à la racine du projet. Ce fichier est couvert par la
règle Git `.env.*` et ne doit jamais être ajouté de force. Le client Prospect
lit uniquement les deux noms ci-dessus dans ce fichier ; les variables déjà
présentes dans le processus restent prioritaires. Le `.env` historique et les
variables Supabase des autres modules ne sont ni lus comme repli ni écrasés.

Procédure locale :

1. ouvrir `.env.prospect.local` directement dans VS Code ;
2. renseigner l'URL DEV et la clé `sb_secret_` sans les copier dans un terminal ;
3. enregistrer puis fermer le fichier ;
4. vérifier avec `git check-ignore -v .env.prospect.local` qu'il reste ignoré ;
5. démarrer Flask normalement depuis le même répertoire.

La migration révoque les droits de `anon` et `authenticated`, puis accorde au
seul rôle `service_role` les opérations nécessaires. Les quatre tables doivent
également être autorisées explicitement dans la configuration Data API du
projet DEV ; un `GRANT` SQL ne rend pas accessible un schéma exclu de PostgREST.

La clé `service_role` contourne RLS. L'isolation effective dépend donc aussi du
filtre `user_id` présent dans chaque requête du repository. La clé ne doit
jamais être placée dans React, un log ou le dépôt Git.

## Garanties transactionnelles

La suppression d'un prospect `do_not_contact` est protégée dans PostgreSQL par
un trigger `BEFORE DELETE`. La création des empreintes d'opposition et la
suppression appartiennent à la même transaction : si aucune empreinte stable
n'est disponible ou si l'insertion échoue, le `DELETE` échoue également.

L'enregistrement d'un import n'est pas encore entièrement atomique :

1. le repository recherche les doublons et oppositions ;
2. il insère la ligne d'import ;
3. il insère les prospects en lot ;
4. si l'étape 3 échoue, il tente de supprimer l'import par compensation.

Les index uniques empêchent les doublons lors d'une course concurrente, mais
le client reçoit actuellement une indisponibilité générique. Si la suppression
compensatoire échoue, une ligne d'import sans prospect peut subsister. Un
import ne contenant que des doublons crée également une ligne d'import sans
prospect sauvegardé.

Avant production, ces opérations devront être regroupées dans une fonction
PostgreSQL/RPC transactionnelle qui retourne distinctement les contacts créés,
déjà présents et opposés.

## État de validation au 14 octobre 2026

La migration a été exécutée uniquement sur le projet DEV indépendant. Les
quatre tables, RLS, privilèges et triggers ont été contrôlés. Le script
transactionnel `supabase/validate_gabriel_prospect_mvp3_dev.sql` a retourné
`overall_result = PASS` sans conserver ses données fictives.

La connexion applicative et la persistance réelle ont ensuite été validées sur
ce même projet DEV avec `examples/gabriel_prospect_demo_5_agences.csv` :

- lecture réussie des quatre tables via le client serveur dédié ;
- cinq agences fictives sauvegardées puis rechargées ;
- quatre fiches qualifiées et une fiche `to_enrich` ;
- réimport reconnu comme cinq doublons sans duplication ;
- transitions `qualified` → `contact_ready` → `contacted` → `replied` et
  historique associé rechargés depuis PostgreSQL ;
- prise de contact refusée pour la fiche `to_enrich` ;
- mêmes contacts autorisés pour un autre utilisateur, sans lecture croisée ;
- passage en `do_not_contact`, réactivation refusée, suppression de la fiche et
  conservation de l'empreinte d'opposition ;
- réimport et insertion directe de l'identifiant opposé refusés ;
- données temporaires du second utilisateur nettoyées, empreinte d'opposition
  fictive volontairement conservée.

Le validateur reproductible
`scripts/validate_gabriel_prospect_mvp3_live.py` épingle une empreinte du point
de terminaison DEV approuvé afin de refuser une exécution accidentelle sur un
autre projet. Il ne journalise ni URL ni clé. Après validation, la base contient
les cinq agences de démonstration, huit événements et une empreinte
d'opposition fictive.

Contrôles locaux après connexion :

- `supabase==2.32.0` sous Python 3.13.5 et `pip check` sans conflit ;
- initialisation réelle du client dédié sans repli sur le Supabase historique ;
- parcours HTTP Flask utilisé par React validé : prévisualisation `200`,
  sauvegarde `201` et cinq doublons signalés ;
- 186 tests backend Prospect, sécurité et isolation réussis ;
- 11 tests de la vue React Prospect réussis ;
- 234 tests React réussis en exécution séquentielle ;
- build Gabriel V2 réussi ;
- analyse des fichiers versionnés et non ignorés : aucune occurrence de l'URL
  complète ni de la clé dédiée.

La passe React parallèle a dépassé le délai de cinq secondes sur cinq tests
historiques Psychologue/AppShell. Les quatre fichiers concernés réussissent
isolément (76 tests) et la suite complète réussit avec un seul worker : il
s'agit d'une limite de temps sous charge locale, pas d'une régression Prospect
identifiée.
