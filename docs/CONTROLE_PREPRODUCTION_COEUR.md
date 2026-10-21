# Contrôle local de préproduction — cœur Gabriel

État observé sur `V3_steph`, sans déploiement ni connexion aux services de production.

| Contrôle | État local | Validation externe requise |
|---|---|---|
| Authentification | garde de démarrage en production, sessions sécurisées, OAuth avec `state` | tester inscription, connexion, déconnexion et récupération sur le domaine final |
| Autorisations | toutes les lectures cœur passent un `user_id`; tests d'isolation présents | confirmer les migrations et RLS réellement appliquées dans le projet de préproduction/production |
| Google OAuth | flux OIDC et URL HTTPS gérés | confirmer identifiants, origine et URI de redirection dans Google Cloud |
| Secrets | `.env.example` ne contient que des valeurs factices; secret Flask vérifié au démarrage | auditer les variables de l'hébergeur et la séparation des projets DEV/production |
| Routes | routes sensibles protégées par les décorateurs d'authentification; Prospect non enregistré en production | scanner le domaine final et vérifier les 401/404 attendus |
| Journalisation | événements structurés disponibles et erreurs fonctionnelles journalisées | centralisation, rétention, alertes et absence de données personnelles à confirmer |
| Monitoring | endpoint `/health` présent | ajouter/valider supervision externe, alertes de latence, taux de 5xx et files IA |
| Incidents | reprise des jobs interrompus et messages de relance | nommer le responsable, le canal, les seuils et la procédure de notification |
| Légal | brouillons créés dans `docs/BROUILLONS_LEGAUX.md` | compléter, faire valider et publier les pages accessibles depuis chaque écran public |
| Coûts IA | crédits, rate limits et plafond de concurrence applicatif présents | fixer budgets fournisseur, alertes, modèles autorisés et plafond monétaire |
| Hébergement | un worker / huit threads / timeout 300 s documentés | tester redémarrage, sauvegarde, saturation, disponibilité et restauration |
| Prospect | désactivé par défaut et impossible à activer en production | vérifier le bundle et les routes sur l'URL de préproduction finale |

## Points bloquants pour un lancement public

1. L'état réel des RLS et migrations distantes n'est pas vérifiable hors du tableau Supabase.
2. Google OAuth, les secrets et la séparation DEV/production ne sont pas vérifiés sur l'hébergeur.
3. Il n'existe pas encore de pages légales publiées et complétées.
4. Le monitoring externe, l'astreinte incident et les budgets fournisseur ne sont pas démontrés.
5. La configuration actuelle à un seul worker tolère une bêta limitée, mais doit être testée sous charge et au redémarrage avant ouverture publique.
