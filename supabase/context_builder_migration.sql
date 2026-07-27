-- ══════════════════════════════════════════════════════════════════════════════
-- GABRIEL — CONTEXT BUILDER ARCHITECTURE — Migration V1.1 : Business Context Store
-- ══════════════════════════════════════════════════════════════════════════════
-- Remplace le stockage actuel (fichiers JSON dans data/contexts/{user_id}.json,
-- non garanti persistant sur Render) par un vrai stockage Supabase.
--
-- Idempotente : peut être exécutée plusieurs fois sans erreur.
-- À copier dans le SQL Editor Supabase et exécuter une fois.
--
-- Trois tables :
--   1. gabriel_context_sessions  — une session de conversation (peut être reprise)
--   2. gabriel_context_messages  — l'historique de la conversation (pour la reprise)
--   3. gabriel_context_fields    — les faits structurés, durables, un par champ
--                                   (source de vérité envoyée au Stratège)
--
-- ── NOTE DE SÉCURITÉ IMPORTANTE (à ne jamais oublier) ─────────────────────────
-- La clé SUPABASE_KEY utilisée par ce backend est une clé "sb_secret_..." —
-- l'équivalent service_role : elle CONTOURNE TOTALEMENT RLS par conception.
-- Les politiques RLS ci-dessous sont donc une défense en profondeur / de la
-- documentation d'intention — PAS la barrière de sécurité réelle. Le SEUL
-- rempart effectif est le filtre `.eq('user_id', uid)` appliqué dans CHAQUE
-- requête côté Python (api/db.py). Ne jamais retirer ce filtre en pensant que
-- RLS suffit — RLS ne s'applique pas ici.
-- ══════════════════════════════════════════════════════════════════════════════


-- ═══════════════════════════════════════════════════════════════
-- 1. gabriel_context_sessions
-- ═══════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS gabriel_context_sessions (
    id                uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id        text        UNIQUE NOT NULL,
    user_id           text        NOT NULL,
    folder_id         text        DEFAULT '',
    status            text        NOT NULL DEFAULT 'active',
    -- active | completed
    current_dimension text        DEFAULT '',   -- clé de la dimension en cours (voir schema.py)
    created_at        timestamptz NOT NULL DEFAULT now(),
    updated_at        timestamptz NOT NULL DEFAULT now(),
    completed_at      timestamptz
);

CREATE INDEX IF NOT EXISTS idx_gabriel_ctx_sessions_user   ON gabriel_context_sessions (user_id);
CREATE INDEX IF NOT EXISTS idx_gabriel_ctx_sessions_sid    ON gabriel_context_sessions (session_id);
CREATE INDEX IF NOT EXISTS idx_gabriel_ctx_sessions_status ON gabriel_context_sessions (user_id, status);

ALTER TABLE gabriel_context_sessions ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "gabriel_ctx_sessions_select_own" ON gabriel_context_sessions;
CREATE POLICY "gabriel_ctx_sessions_select_own"
ON gabriel_context_sessions FOR SELECT
USING (auth.uid()::text = user_id);

DROP POLICY IF EXISTS "gabriel_ctx_sessions_insert_own" ON gabriel_context_sessions;
CREATE POLICY "gabriel_ctx_sessions_insert_own"
ON gabriel_context_sessions FOR INSERT
WITH CHECK (auth.uid()::text = user_id);

DROP POLICY IF EXISTS "gabriel_ctx_sessions_update_own" ON gabriel_context_sessions;
CREATE POLICY "gabriel_ctx_sessions_update_own"
ON gabriel_context_sessions FOR UPDATE
USING (auth.uid()::text = user_id)
WITH CHECK (auth.uid()::text = user_id);

DROP POLICY IF EXISTS "gabriel_ctx_sessions_delete_own" ON gabriel_context_sessions;
CREATE POLICY "gabriel_ctx_sessions_delete_own"
ON gabriel_context_sessions FOR DELETE
USING (auth.uid()::text = user_id);


-- ═══════════════════════════════════════════════════════════════
-- 2. gabriel_context_messages — historique conversationnel (reprise de session)
-- ═══════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS gabriel_context_messages (
    id            uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id    text        NOT NULL,
    user_id       text        NOT NULL,
    role          text        NOT NULL,     -- user | assistant
    content       text        NOT NULL,
    dimension_key text        DEFAULT '',   -- dimension concernée au moment du message
    created_at    timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_gabriel_ctx_msgs_session ON gabriel_context_messages (session_id, created_at);
CREATE INDEX IF NOT EXISTS idx_gabriel_ctx_msgs_user    ON gabriel_context_messages (user_id);

ALTER TABLE gabriel_context_messages ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "gabriel_ctx_msgs_select_own" ON gabriel_context_messages;
CREATE POLICY "gabriel_ctx_msgs_select_own"
ON gabriel_context_messages FOR SELECT
USING (auth.uid()::text = user_id);

DROP POLICY IF EXISTS "gabriel_ctx_msgs_insert_own" ON gabriel_context_messages;
CREATE POLICY "gabriel_ctx_msgs_insert_own"
ON gabriel_context_messages FOR INSERT
WITH CHECK (auth.uid()::text = user_id);

DROP POLICY IF EXISTS "gabriel_ctx_msgs_delete_own" ON gabriel_context_messages;
CREATE POLICY "gabriel_ctx_msgs_delete_own"
ON gabriel_context_messages FOR DELETE
USING (auth.uid()::text = user_id);


-- ═══════════════════════════════════════════════════════════════
-- 3. gabriel_context_fields — faits structurés durables (Organization Context)
-- ═══════════════════════════════════════════════════════════════
-- Un champ = la dernière valeur connue pour ce user_id + field_key (upsert).
-- field_key doit correspondre à une clé de ALL_FIELD_KEYS (schema.py) —
-- vérifié côté application, pas en contrainte SQL (le schéma évolue en code).

CREATE TABLE IF NOT EXISTS gabriel_context_fields (
    id                uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id           text        NOT NULL,
    field_key         text        NOT NULL,
    value             text        NOT NULL,
    status            text        NOT NULL DEFAULT 'extracted',
    -- extracted | confirmed  (V1.2 ajoutera : inferred | outdated | conflicted)
    confidence        real        NOT NULL DEFAULT 1.0,
    source_session_id text        DEFAULT '',
    created_at        timestamptz NOT NULL DEFAULT now(),
    updated_at        timestamptz NOT NULL DEFAULT now(),
    UNIQUE (user_id, field_key)
);

CREATE INDEX IF NOT EXISTS idx_gabriel_ctx_fields_user ON gabriel_context_fields (user_id);

ALTER TABLE gabriel_context_fields ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "gabriel_ctx_fields_select_own" ON gabriel_context_fields;
CREATE POLICY "gabriel_ctx_fields_select_own"
ON gabriel_context_fields FOR SELECT
USING (auth.uid()::text = user_id);

DROP POLICY IF EXISTS "gabriel_ctx_fields_insert_own" ON gabriel_context_fields;
CREATE POLICY "gabriel_ctx_fields_insert_own"
ON gabriel_context_fields FOR INSERT
WITH CHECK (auth.uid()::text = user_id);

DROP POLICY IF EXISTS "gabriel_ctx_fields_update_own" ON gabriel_context_fields;
CREATE POLICY "gabriel_ctx_fields_update_own"
ON gabriel_context_fields FOR UPDATE
USING (auth.uid()::text = user_id)
WITH CHECK (auth.uid()::text = user_id);

DROP POLICY IF EXISTS "gabriel_ctx_fields_delete_own" ON gabriel_context_fields;
CREATE POLICY "gabriel_ctx_fields_delete_own"
ON gabriel_context_fields FOR DELETE
USING (auth.uid()::text = user_id);
