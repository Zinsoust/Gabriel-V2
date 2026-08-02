-- ─── Gabriel — Crédits utilisateur (solde partagé Psychologue/Stratège/Créateur) ───
--
-- 300 crédits offerts à l'inscription. La colonne DEFAULT s'applique aussi
-- rétroactivement aux comptes déjà existants (Postgres backfill à l'ALTER).

ALTER TABLE gabriel_users
  ADD COLUMN IF NOT EXISTS credits INTEGER NOT NULL DEFAULT 300;

UPDATE gabriel_users SET credits = 300 WHERE credits IS NULL;
