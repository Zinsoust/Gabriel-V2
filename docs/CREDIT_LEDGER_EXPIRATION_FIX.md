# Correction P0 — crédits réservés expirés

## Cause racine

La phase 1 expirait uniquement `remaining_credits`, c'est-à-dire la partie
encore disponible d'un lot. La partie déplacée dans `reserved_credits` restait
sans état d'expiration durable. Lors d'une libération ou d'une capture
partielle, cette partie non consommée était systématiquement ajoutée à nouveau
à `remaining_credits` et au solde disponible du compte.

## Règle financière

Une réservation garantit que la consommation fournisseur réellement confirmée
peut être capturée. À la finalisation :

- la partie capturée est consommée normalement ;
- la partie non consommée d'un lot actif retourne au solde disponible ;
- la partie non consommée d'un lot expiré est comptabilisée comme expirée et
  ne retourne jamais au solde disponible.

Les allocations distinguent désormais `captured_credits`, `released_credits`
et `expired_credits`. Leur somme ne peut pas dépasser la réservation initiale.

## État durable et cutoff

`gabriel_credit_grants` reçoit `expired_at` et `expiration_cutoff`. Une fois
renseigné, cet état est irréversible. Les libérations et captures consultent cet
état au lieu de recalculer exclusivement l'expiration depuis l'horloge.

`gabriel_credit_expire_grants(p_cutoff)` considère le cutoff comme une décision
administrative autoritative. En production, le scheduler doit transmettre
`clock_timestamp()` et ne doit pas anticiper les expirations. Un cutoff futur
est refusé à `service_role` seul. Il exige simultanément une session PostgreSQL
superutilisateur et une référence non vide (200 caractères maximum) placée dans
`gabriel.credit_expiration_future_cutoff_approval`. Cette référence et
`session_user` sont consignés dans l'événement append-only. Les tests isolés
peuvent satisfaire ce contrat avec leur administrateur synthétique. En
production, la référence doit correspondre à une approbation métier externe :
la base prouve sa présence, pas la validité du processus d'approbation.

Si l'heure réelle d'expiration est dépassée avant le passage du scheduler, la
libération ou la capture marque elle-même le lot comme expiré dans la même
transaction avant de finaliser les allocations.

La libération et la capture acquièrent d'abord, dans l'ordre existant, les
verrous sur la réservation et le compte, puis tous les couples allocation/lot
concernés dans un ordre stable. Elles prennent ensuite un unique
`clock_timestamp()` de finalisation. Ce point constitue la linéarisation : un
lot qui expire pendant une attente de verrou est donc traité comme expiré ; un
lot qui expire après ce point reste actif pour cette finalisation atomique.

## Historique et idempotence

Le ledger reste append-only. Deux phases d'expiration peuvent être consignées :

- `grant_expiration` retire la partie encore disponible et fixe l'état durable ;
- `reserved_finalisation` retire la partie réservée devenue inutilisable.

Une répétition de l'expiration ou de la finalisation ne crée aucun événement
supplémentaire. Les anciennes lignes d'expiration servent uniquement à remplir
les nouvelles colonnes d'état ; aucun ancien événement ou solde n'est réécrit.

## Migration

`supabase/20261026_credit_ledger_expiration_fix.sql` est additive et doit être
appliquée après la migration Phase 1, sous le propriétaire dédié. Elle :

1. ajoute les colonnes d'état et de ventilation ;
2. ajoute et valide les contraintes de conservation ;
3. reconstitue l'état des lots ayant déjà un événement `expire` ;
4. remplace les trois RPC concernées sans modifier leurs signatures ;
5. réaffirme les révocations et les droits `service_role` uniquement.

Elle ne modifie aucune politique RLS et ne donne aucun accès direct aux tables.
Elle n'est pas appliquée automatiquement par la présence du fichier.
