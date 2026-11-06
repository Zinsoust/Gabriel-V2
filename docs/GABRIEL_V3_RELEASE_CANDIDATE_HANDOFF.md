# Gabriel V3 — passation du release candidate

Date : 6 novembre 2026

Branche proposée : `release/gabriel-v3-rc-2026-11-07`

Le SHA immuable du release candidate doit être transmis avec ce document après création autorisée des commits et vérifié avec `git rev-parse HEAD`.

Ce release candidate réutilise l'application existante : Flask sert les pages publiques, les API et le bundle React V2 déjà compilé dans `static/gabriel-v2/`. Lovable n'est pas requis pour ce déploiement.

## 1. Récupérer sans écraser une autre version

```bash
git fetch steph
git switch --detach <RC_SHA>
```

Ne pas fusionner ce commit dans `main` pour déployer. Render doit pointer directement sur la branche et le commit validés.

## 2. Paramètres Render — Web Service

- Dépôt : `https://github.com/Zinsoust/Gabriel-V2`
- Branche : `release/gabriel-v3-rc-2026-11-07`
- Runtime : `Python 3`
- Root Directory : laisser vide
- Build Command : `pip install -r requirements.txt`
- Start Command : `gunicorn app:app --bind 0.0.0.0:$PORT --workers 1 --threads 8 --timeout 300 --worker-tmp-dir /dev/shm`
- Health Check Path : `/health`
- Python : `3.13.5` via `.python-version`
- Pre-Deploy Command : laisser vide — aucune migration automatique

Le frontend React est déjà compilé. Pour régénérer volontairement le bundle avant un futur commit :

```bash
cd frontend-react
npm install
npm run build:gabriel-v2
```

Le dépôt n'a pas encore de lockfile npm : ne pas reconstruire le bundle pendant le déploiement du RC. Utiliser les fichiers `static/gabriel-v2/app.js` et `app.css` validés et commités.

## 3. Variables — niveau 1, site public sûr

Définir dans Render, jamais dans GitHub :

```text
FLASK_SECRET_KEY=<secret aléatoire long>
APP_URL=https://<service-ou-domaine>
GABRIEL_ENV=production
AUTH_ENABLED=true
GABRIEL_ACCOUNTS_ENABLED=false
RATE_LIMIT_ENABLED=true
GABRIEL_PROSPECT_ENABLED=false
MEMORY_SHARE_ACROSS_USERS=false
GABRIEL_PAID_AI_ENABLED=false
GABRIEL_PROVIDER_COST_GUARD_ENABLED=false
GABRIEL_CREDIT_LEDGER_ENABLED=false
MISTRAL_VALIDATION_BUDGET_ENABLED=false
NLP_PRELOAD=false
RAG_PRELOAD=false
```

Ce niveau publie les pages publiques et garde toute l'application privée fermée. La page de connexion explique que l'accès n'est pas encore ouvert. Prospect et tous les appels fournisseurs payants restent désactivés.

## 4. Niveau 2 — bêta restreinte

Avant de passer `GABRIEL_ACCOUNTS_ENABLED=true` :

1. Utiliser un projet Supabase de préproduction sauvegardé, pas la production directement.
2. Configurer `SUPABASE_URL` et `SUPABASE_KEY` dans Render. `SUPABASE_KEY` est une clé serveur : ne jamais l'exposer au frontend, à Lovable ou au navigateur.
3. Vérifier que les tables attendues par `api/db.py` existent et que les migrations applicables ont été relues puis exécutées manuellement.
4. Valider l'isolation de deux comptes réels de test et les droits backend-only. Les tests locaux ne certifient pas le Supabase distant.
5. Configurer éventuellement `GOOGLE_CLIENT_ID` et `GOOGLE_CLIENT_SECRET`, puis autoriser exactement :
   `https://<APP_URL>/auth/google/callback`.
6. Garder tous les flags IA et financiers à `false`.
7. Activer `GABRIEL_ACCOUNTS_ENABLED=true`, redéployer, puis tester connexion, déconnexion, dossiers, historique et suppression de compte.

Le code ne fournit pas encore une gestion complète d'invitations. Pour une bêta strictement nominative, restreindre l'accès au service au niveau Render/proxy ou ajouter et tester une allowlist avant ouverture.

## 5. Niveau 3 — fonctions IA et ouverture commerciale

Ne pas activer avant validation sur l'environnement ciblé :

- migrations `20261024_credit_ledger_phase1.sql`, `20261026_credit_ledger_expiration_fix.sql` et `20261028_provider_budget_guard.sql` exécutées manuellement et certifiées ;
- sécurité backend-only de `20261029_preproduction_backend_only_security.sql` vérifiée ;
- politiques de plafond fournisseur créées dans PostgreSQL ;
- prix et budgets d'opération explicitement renseignés ;
- `SUPABASE_SERVICE_ROLE_KEY` disponible uniquement côté Render ;
- authentification, isolation, concurrence, réservations/captures et reprise après erreur testées sur ce Supabase ;
- clés fournisseur configurées et plafond commercial approuvé.

Seulement ensuite, selon la procédure financière validée :

```text
GABRIEL_CREDIT_LEDGER_ENABLED=true
GABRIEL_PROVIDER_COST_GUARD_ENABLED=true
GABRIEL_PAID_AI_ENABLED=true
```

L'ordre est important. Une configuration incomplète doit empêcher l'appel fournisseur.

## 6. Psychologue — contrôle après déploiement

Niveau 1 :

- `GET /health` → `200` ;
- `GET /` → `200` ;
- `GET /login` → page fermée, sans formulaire de mot de passe ;
- `GET /orchestrateur` → redirection vers la page d'accès fermé ;
- aucun appel Mistral, YouTube ou RapidAPI dans les logs.

Niveau 2 :

- connexion d'un compte de test autorisé ;
- ouverture `/orchestrateur?agent=psychologue` ;
- aperçu `preview_only` avec verbatims synthétiques ;
- vérification qu'un second compte ne voit ni job, ni analyse, ni dossier du premier ;
- simulation d'une indisponibilité Supabase et contrôle des erreurs fail-closed.

Niveau 3 : lancer au maximum une analyse synthétique après approbation du plafond, vérifier polling, résultat, débit/capture et absence de double appel avec la même clé d'idempotence.

## 7. Lovable

Le frontend React fourni fonctionne directement avec Flask en même origine et doit être privilégié pour ce RC. Un frontend Lovable séparé n'est pas interchangeable sans travail supplémentaire : les cookies de session, les contrôles d'origine et les en-têtes `Idempotency-Key` supposent actuellement la même origine.

Ne jamais placer `SUPABASE_KEY`, `SUPABASE_SERVICE_ROLE_KEY`, une clé IA ou `FLASK_SECRET_KEY` dans Lovable. Une intégration ultérieure doit conserver les contrats API existants et passer par un domaine/proxy approuvé.

## 8. GO / NO-GO et retour arrière

- Site public : **GO** avec `GABRIEL_ACCOUNTS_ENABLED=false` et tous les flags payants à `false`.
- Comptes : **NO-GO** tant que Supabase réel, isolation et accès restreint ne sont pas validés ; **GO bêta** après la checklist du niveau 2.
- IA réelle : **NO-GO** tant que ledger, garde, politiques de plafond, prix et clés ne sont pas validés sur l'environnement ; **GO limité** après la checklist du niveau 3.

En cas de régression :

1. remettre immédiatement `GABRIEL_ACCOUNTS_ENABLED=false` et `GABRIEL_PAID_AI_ENABLED=false` ;
2. dans Render, redéployer le dernier commit connu comme sain ;
3. vérifier `/health` et `/` ;
4. ne jamais annuler automatiquement une migration de données : restaurer depuis une sauvegarde validée selon la procédure Supabase.
