-- ─── Gabriel — Supabase Row Level Security (RLS) ─────────────────────────────
--
-- À exécuter dans : Supabase Dashboard → SQL Editor
-- Ou via : supabase db push (si CLI configurée)
--
-- Ces policies garantissent qu'un utilisateur ne peut accéder
-- qu'à SES propres données, même en cas de bug côté backend.
--
-- ATTENTION : ces policies s'appliquent avec la clé ANON (client-side).
-- La clé SERVICE ROLE bypass les RLS — ne jamais l'exposer côté client.
-- ─────────────────────────────────────────────────────────────────────────────


-- ══════════════════════════════════════════════════════════════════════════════
-- TABLE : gabriel_analyses
-- ══════════════════════════════════════════════════════════════════════════════

ALTER TABLE gabriel_analyses ENABLE ROW LEVEL SECURITY;

-- Lecture : uniquement ses propres analyses
CREATE POLICY "gabriel_analyses_select_own"
ON gabriel_analyses
FOR SELECT
USING (auth.uid()::text = user_id);

-- Insertion : uniquement pour soi-même
CREATE POLICY "gabriel_analyses_insert_own"
ON gabriel_analyses
FOR INSERT
WITH CHECK (auth.uid()::text = user_id);

-- Mise à jour : uniquement ses propres analyses
CREATE POLICY "gabriel_analyses_update_own"
ON gabriel_analyses
FOR UPDATE
USING (auth.uid()::text = user_id)
WITH CHECK (auth.uid()::text = user_id);

-- Suppression : uniquement ses propres analyses
CREATE POLICY "gabriel_analyses_delete_own"
ON gabriel_analyses
FOR DELETE
USING (auth.uid()::text = user_id);


-- ══════════════════════════════════════════════════════════════════════════════
-- TABLE : gabriel_strategies
-- ══════════════════════════════════════════════════════════════════════════════

ALTER TABLE gabriel_strategies ENABLE ROW LEVEL SECURITY;

CREATE POLICY "gabriel_strategies_select_own"
ON gabriel_strategies
FOR SELECT
USING (auth.uid()::text = user_id);

CREATE POLICY "gabriel_strategies_insert_own"
ON gabriel_strategies
FOR INSERT
WITH CHECK (auth.uid()::text = user_id);

CREATE POLICY "gabriel_strategies_update_own"
ON gabriel_strategies
FOR UPDATE
USING (auth.uid()::text = user_id)
WITH CHECK (auth.uid()::text = user_id);

CREATE POLICY "gabriel_strategies_delete_own"
ON gabriel_strategies
FOR DELETE
USING (auth.uid()::text = user_id);


-- ══════════════════════════════════════════════════════════════════════════════
-- TABLE : gabriel_feedbacks
-- ══════════════════════════════════════════════════════════════════════════════

ALTER TABLE gabriel_feedbacks ENABLE ROW LEVEL SECURITY;

CREATE POLICY "gabriel_feedbacks_select_own"
ON gabriel_feedbacks
FOR SELECT
USING (auth.uid()::text = user_id);

CREATE POLICY "gabriel_feedbacks_insert_own"
ON gabriel_feedbacks
FOR INSERT
WITH CHECK (auth.uid()::text = user_id);

-- Feedbacks : pas de UPDATE ni DELETE (données analytics immuables)


-- ══════════════════════════════════════════════════════════════════════════════
-- TABLE : gabriel_exports
-- ══════════════════════════════════════════════════════════════════════════════

ALTER TABLE gabriel_exports ENABLE ROW LEVEL SECURITY;

CREATE POLICY "gabriel_exports_select_own"
ON gabriel_exports
FOR SELECT
USING (auth.uid()::text = user_id);

CREATE POLICY "gabriel_exports_insert_own"
ON gabriel_exports
FOR INSERT
WITH CHECK (auth.uid()::text = user_id);

CREATE POLICY "gabriel_exports_delete_own"
ON gabriel_exports
FOR DELETE
USING (auth.uid()::text = user_id);


-- ══════════════════════════════════════════════════════════════════════════════
-- TABLE : gabriel_users
-- ══════════════════════════════════════════════════════════════════════════════

ALTER TABLE gabriel_users ENABLE ROW LEVEL SECURITY;

-- Un utilisateur ne peut lire que son propre profil
CREATE POLICY "gabriel_users_select_own"
ON gabriel_users
FOR SELECT
USING (auth.uid()::text = user_id);

-- Mise à jour : uniquement son propre profil
CREATE POLICY "gabriel_users_update_own"
ON gabriel_users
FOR UPDATE
USING (auth.uid()::text = user_id)
WITH CHECK (auth.uid()::text = user_id);

-- Insertion : autorisée pour inscription (auth.uid() peut être null lors du register)
-- La vérification user_id = auth.uid() se fait côté backend (api/auth.py)
CREATE POLICY "gabriel_users_insert_own"
ON gabriel_users
FOR INSERT
WITH CHECK (true);  -- backend enforces user_id = generated UUID


-- ══════════════════════════════════════════════════════════════════════════════
-- VÉRIFICATION — à exécuter pour confirmer que RLS est actif
-- ══════════════════════════════════════════════════════════════════════════════
-- SELECT tablename, rowsecurity FROM pg_tables
-- WHERE schemaname = 'public'
-- AND tablename LIKE 'gabriel_%';


-- ══════════════════════════════════════════════════════════════════════════════
-- NOTE SUR LA CLÉ user_id
-- ══════════════════════════════════════════════════════════════════════════════
-- Les tables utilisent user_id TEXT (UUID stocké comme string côté Python).
-- auth.uid() retourne un UUID natif Postgres.
-- Le cast ::text est nécessaire pour la comparaison.
--
-- Si Supabase Auth est utilisé directement (magic link, password), auth.uid()
-- sera automatiquement rempli. Si l'auth est custom (Google OAuth + backend),
-- il faut s'assurer que le JWT Supabase est passé dans les requêtes,
-- ou utiliser la clé SERVICE ROLE côté backend uniquement.
--
-- Pour une beta fermée sans Supabase Auth natif :
-- Les RLS protègent en dernier recours. La sécurité principale reste
-- l'isolation user_id dans chaque requête backend (api/db.py).
