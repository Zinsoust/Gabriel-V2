# Gabriel V3 — Ledger de crédits, phase 1

Statut : socle local, non branché aux routes applicatives.

Le feature flag `GABRIEL_CREDIT_LEDGER_ENABLED` est désactivé par défaut. La
présence de la migration ou l'import de `core.credit_ledger` ne modifie donc ni
les soldes actuels, ni le comportement des agents.

## Invariants

1. Aucun solde disponible ou réservé ne peut être négatif.
2. Une réservation retire les crédits disponibles avant tout appel fournisseur.
3. Une clé d'idempotence appartient à un utilisateur et à un contenu précis.
4. Une répétition identique retourne la réservation existante ; une répétition
   différente est rejetée.
5. Une libération complète n'est possible que si aucun appel fournisseur n'a
   commencé.
6. Une dépense réseau ambiguë reste réservée dans l'état `uncertain`.
7. Une capture ne peut pas dépasser la réservation ni la consommation
   fournisseur enregistrée.
8. Le ledger financier est append-only.
9. Les lots expirent uniquement pour leur partie encore disponible ; les
   réservations en cours restent réconciliables.
10. L'import historique est explicite, unique et n'écrit jamais dans
    `gabriel_users.credits`.

## Artifacts

- `supabase/20261024_credit_ledger_phase1.sql` : schéma PostgreSQL, contraintes,
  RLS et RPC atomiques. Cette migration n'est pas exécutée automatiquement.
- `core/credit_ledger.py` : implémentation SQLite persistante réservée aux tests
  locaux et à la validation du contrat transactionnel.
- `core/credit_economics.py` : calcul pur de l'enveloppe maximale de crédits,
  sans quantité commerciale codée en dur.

Le backend SQLite exige un chemin explicite. Il ne crée donc aucun fichier dans
`data/` et ne peut pas remplacer silencieusement le stockage de production.

## Budget économique provisoire

Le calcul impose :

- marge contributive minimale : 70 % du revenu HT ;
- autres coûts variables : 5 % du revenu HT ;
- réserve de sécurité supplémentaire : 2 % du revenu HT ;
- plafond fournisseur indicatif : 0,05 € par crédit ;
- TVA : 20 %.

Les résultats ci-dessous sont des plafonds mathématiques, pas des offres
commerciales validées :

| Prix TTC | Stripe 2,2 % + 0,25 € | Stress 5,85 % + 0,25 € |
|---:|---:|---:|
| 29 € | 93 crédits maximum | 72 crédits maximum |
| 49 € | 161 crédits maximum | 125 crédits maximum |
| 99 € | 330 crédits maximum | 258 crédits maximum |

Le stress inclut paiement international, conversion et Stripe Billing. Les
quantités 80/140/290, 65/115/240 ou toute autre grille ne sont définies ni dans
le code ni dans la migration.

## Barèmes encore non certifiés

Les poids proposés lors de l'audit ne deviennent pas des constantes de
production pendant cette phase. Ils doivent être validés sur la consommation
physique mesurée :

| Opération | Plafond précédemment envisagé | État phase 1 |
|---|---:|---|
| Psychologue | 2 crédits | À mesurer sur Small 4 versionné |
| Ariane | 5 crédits | À mesurer sur Large 3 et Large 4 séparément |
| Thomas génération | 12 crédits | À mesurer, y compris gardes et retries |
| Thomas raffinement | 3 crédits | Conditionnel, non certifié |
| Cross | 8 à 10 crédits | Dépend du cache et du nombre de sources |
| Orchestrateur web | 4 crédits | Dépend du modèle et du fournisseur web |
| STT | 1 crédit | Non couvert tant que durée et tarif réels ne sont pas figés |
| TTS | 4 crédits | Non couvert tant que caractères, voix et fallback ne sont pas figés |

La voix et les opérations conditionnelles restent donc **NO-GO économique**.
Une route future devra refuser l'appel si son coût maximal ne peut pas être
calculé avant exécution ou si le tarif fournisseur dépasse l'enveloppe réservée.

## Validation PostgreSQL restant à faire

Les tests de phase 1 exécutent une base SQLite isolée et vérifient le contrat
textuel de la migration. Avant toute application distante, il faudra encore :

1. démarrer une base PostgreSQL/Supabase locale jetable ;
2. appliquer la migration dans cette base uniquement ;
3. rejouer les tests de concurrence directement contre les RPC SQL ;
4. vérifier les plans de verrouillage et les contraintes RLS avec les rôles
   `anon`, `authenticated` et `service_role` ;
5. comparer les sommes des lots aux comptes après chaque scénario ;
6. faire relire et approuver séparément le script d'import historique.
