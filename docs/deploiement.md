# Gabriel.ai — mettre en ligne et ouvrir à d'autres utilisateurs

Ce document dit ce qu'il faut vérifier **avant** d'inviter quelqu'un, et pourquoi. Il complète
`beta_security_protocol.md` (règles d'usage des testeurs) et `.env.example` (toutes les variables).

## 1. Ce qui protège vos utilisateurs (et ce qui les exposerait)

| Réglage | Effet | À faire |
|---|---|---|
| `AUTH_ENABLED=true` | Sans lui, **tout visiteur devient le même utilisateur de développement** : analyses, crédits et stratégies partagés, sans connexion. | Obligatoire. Un serveur déclaré déployé (`RENDER` ou `GABRIEL_ENV=production`) **refuse de démarrer** sans lui. |
| `FLASK_SECRET_KEY` | Signe les sessions. Trop courte ou d'exemple : une session peut être falsifiée. | 24 caractères minimum, aléatoire. Le démarrage est refusé en déploiement si elle est faible. |
| `SUPABASE_KEY` | Le serveur utilise une clé **secrète** (`sb_secret_…`) qui contourne les règles d'accès de la base. | Ne jamais l'envoyer au navigateur ni la commiter. L'isolation entre utilisateurs repose donc sur le code (voir §3). |
| `MEMORY_SHARE_ACROSS_USERS` | Par défaut `false` : la mémoire stratégique (offre, prix, décision) reste propre à chaque compte. | Ne le passer à `true` que si tous les comptes appartiennent à la même équipe. |
| Webhook Stripe | La signature est vérifiée. | Renseigner `STRIPE_WEBHOOK_SECRET`. |

## 2. Capacité : ce qui limite le nombre d'utilisateurs simultanés

- **Un seul worker** (`Procfile` : `--workers 1 --threads 8`). Les travaux en cours vivent en mémoire de ce
  processus. Un redémarrage les interrompt : ils sont alors marqués « interrompus » (au démarrage et à la
  lecture) et l'écran propose de relancer. Ne pas monter à plusieurs workers sans déplacer les travaux en base.
- **Mistral** : `MISTRAL_MAX_CONCURRENCY` (défaut 2) et `MISTRAL_MIN_INTERVAL` (défaut 1 s) plafonnent les appels
  du serveur **entier**. Une génération complète du Créateur prend 4 à 6 minutes seule ; plusieurs utilisateurs
  en même temps se partagent ces 2 appels simultanés et attendent davantage. À relever si votre plan le permet.
- **Modèles** : par défaut `mistral-small-latest` et `mistral-large-latest`. Un plan limité n'autorise parfois que
  les modèles `ministral` : fixer `MISTRAL_MODEL_FAST` et `MISTRAL_MODEL_DEEP` (voir `.env.example`).
- **Réseau** : `PREFER_IPV4=true` (défaut) contourne un IPv6 cassé qui bloquait YouTube, Mistral et Supabase.

## 3. Isolation entre utilisateurs — ce qui est vérifié par des tests

`tests/test_isolation_utilisateurs.py` et `tests/test_utilisation_simultanee.py` :
- un utilisateur ne voit, ne modifie ni ne supprime les analyses, stratégies, retours, Cross Analyses ni travaux
  d'un autre, **y compris quand Supabase est indisponible** (repli sur fichier local) ;
- sans connexion, les routes de données répondent 401 ;
- des générations simultanées de plusieurs utilisateurs ne se mélangent pas ;
- la mémoire stratégique d'un compte n'apparaît jamais dans le prompt d'un autre.

## 4. Avant la première invitation

1. Variables du serveur : `AUTH_ENABLED=true`, `FLASK_SECRET_KEY` aléatoire, `APP_URL` en `https://`, clés Supabase,
   Mistral, YouTube, Stripe (`STRIPE_*`), Google OAuth (`GOOGLE_CLIENT_ID/SECRET`).
2. Base Supabase : appliquer les migrations du dossier `supabase/` (dont `security_policies.sql`).
3. Vérifier `GET /health` puis créer **votre propre compte** et parcourir : inscription → analyse → Cross Analyse →
   Créateur → Ariane, sur ordinateur **et** téléphone.
4. Inviter 5 à 10 testeurs au plus (voir `beta_security_protocol.md`), avec un canal de signalement de bugs.

## 5. Si quelque chose semble faux

- Le serveur ne démarre pas et affiche « Démarrage refusé » : c'est voulu, corriger la variable citée.
- Des analyses restent « en cours » : elles sont marquées interrompues au démarrage suivant (`JOB_SWEEP_ON_START=1`).
- Une génération du Créateur échoue avec « format inconnu » : le message liste les formats disponibles.
