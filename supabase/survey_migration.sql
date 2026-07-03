-- ─── Gabriel — Survey & Feedback Loop Migration ──────────────────────────────
--
-- Migration idempotente : peut être rejouée sans risque.
-- Ne supprime aucune table ou policy existante.
-- user_id : TEXT (cohérent avec les tables gabriel existantes)
--
-- À exécuter dans : Supabase Dashboard → SQL Editor
-- ─────────────────────────────────────────────────────────────────────────────


-- ══════════════════════════════════════════════════════════════════════════════
-- TABLE : gabriel_survey_events
-- Trace chaque enquête affichée (quand, pour qui, sur quoi)
-- ══════════════════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS gabriel_survey_events (
    id          uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     text        NOT NULL,
    event_type  text        NOT NULL,           -- 'after_analysis' | 'after_strategy' | 'after_creation' | 'after_chat'
    target_type text,                           -- 'analysis' | 'strategy' | 'content' | 'chat'
    target_id   text,
    status      text        DEFAULT 'shown',    -- 'shown' | 'responded' | 'dismissed' | 'later'
    shown_at    timestamptz DEFAULT now(),
    responded_at timestamptz,
    dismissed_at timestamptz,
    metadata    jsonb       DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_survey_events_user_id  ON gabriel_survey_events(user_id);
CREATE INDEX IF NOT EXISTS idx_survey_events_shown_at ON gabriel_survey_events(shown_at DESC);

ALTER TABLE gabriel_survey_events ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "gabriel_survey_events_select_own" ON gabriel_survey_events;
DROP POLICY IF EXISTS "gabriel_survey_events_insert_own" ON gabriel_survey_events;
DROP POLICY IF EXISTS "gabriel_survey_events_update_own" ON gabriel_survey_events;

CREATE POLICY "gabriel_survey_events_select_own"
ON gabriel_survey_events FOR SELECT
USING (auth.uid()::text = user_id);

CREATE POLICY "gabriel_survey_events_insert_own"
ON gabriel_survey_events FOR INSERT
WITH CHECK (auth.uid()::text = user_id);

CREATE POLICY "gabriel_survey_events_update_own"
ON gabriel_survey_events FOR UPDATE
USING (auth.uid()::text = user_id)
WITH CHECK (auth.uid()::text = user_id);


-- ══════════════════════════════════════════════════════════════════════════════
-- TABLE : gabriel_survey_responses
-- Réponses détaillées de l'utilisateur à une enquête
-- ══════════════════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS gabriel_survey_responses (
    id                  uuid    PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id             text    NOT NULL,
    survey_event_id     text,                   -- référence souple (TEXT) vers gabriel_survey_events.id
    target_type         text,
    target_id           text,
    agent               text,                   -- 'psychologue' | 'stratege' | 'createur' | 'chat'
    quick_answer        text,                   -- 'oui' | 'partiellement' | 'non'
    relevance_score     integer CHECK (relevance_score BETWEEN 1 AND 5),
    clarity_score       integer CHECK (clarity_score BETWEEN 1 AND 5),
    usefulness_score    integer CHECK (usefulness_score BETWEEN 1 AND 5),
    actionability_score integer CHECK (actionability_score BETWEEN 1 AND 5),
    free_feedback       text    CHECK (char_length(free_feedback) <= 2000),
    created_at          timestamptz DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_survey_responses_user_id   ON gabriel_survey_responses(user_id);
CREATE INDEX IF NOT EXISTS idx_survey_responses_agent     ON gabriel_survey_responses(agent);
CREATE INDEX IF NOT EXISTS idx_survey_responses_created   ON gabriel_survey_responses(created_at DESC);

ALTER TABLE gabriel_survey_responses ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "gabriel_survey_responses_select_own" ON gabriel_survey_responses;
DROP POLICY IF EXISTS "gabriel_survey_responses_insert_own" ON gabriel_survey_responses;

CREATE POLICY "gabriel_survey_responses_select_own"
ON gabriel_survey_responses FOR SELECT
USING (auth.uid()::text = user_id);

CREATE POLICY "gabriel_survey_responses_insert_own"
ON gabriel_survey_responses FOR INSERT
WITH CHECK (auth.uid()::text = user_id);


-- ══════════════════════════════════════════════════════════════════════════════
-- TABLE : gabriel_consent_records
-- Historique des consentements produit (RGPD)
-- ══════════════════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS gabriel_consent_records (
    id           uuid    PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id      text    NOT NULL,
    consent_type text    NOT NULL,   -- 'product_improvement' | 'survey' | 'analytics'
    status       text    NOT NULL,   -- 'granted' | 'withdrawn'
    source       text,               -- 'settings' | 'survey_prompt' | 'onboarding'
    created_at   timestamptz DEFAULT now(),
    withdrawn_at timestamptz,
    metadata     jsonb    DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_consent_records_user_id ON gabriel_consent_records(user_id);

ALTER TABLE gabriel_consent_records ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "gabriel_consent_records_select_own" ON gabriel_consent_records;
DROP POLICY IF EXISTS "gabriel_consent_records_insert_own" ON gabriel_consent_records;
DROP POLICY IF EXISTS "gabriel_consent_records_update_own" ON gabriel_consent_records;

CREATE POLICY "gabriel_consent_records_select_own"
ON gabriel_consent_records FOR SELECT
USING (auth.uid()::text = user_id);

CREATE POLICY "gabriel_consent_records_insert_own"
ON gabriel_consent_records FOR INSERT
WITH CHECK (auth.uid()::text = user_id);

CREATE POLICY "gabriel_consent_records_update_own"
ON gabriel_consent_records FOR UPDATE
USING (auth.uid()::text = user_id)
WITH CHECK (auth.uid()::text = user_id);


-- ══════════════════════════════════════════════════════════════════════════════
-- TABLE : gabriel_chat_conversations
-- Conversations chatbot stockées (sans entraînement automatique)
-- ══════════════════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS gabriel_chat_conversations (
    id         uuid    PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id    text    NOT NULL,
    agent      text,                -- 'psychologue' | 'stratege' | 'createur'
    title      text,
    created_at timestamptz DEFAULT now(),
    updated_at timestamptz DEFAULT now(),
    metadata   jsonb   DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_chat_conv_user_id   ON gabriel_chat_conversations(user_id);
CREATE INDEX IF NOT EXISTS idx_chat_conv_created   ON gabriel_chat_conversations(created_at DESC);

ALTER TABLE gabriel_chat_conversations ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "gabriel_chat_conv_select_own" ON gabriel_chat_conversations;
DROP POLICY IF EXISTS "gabriel_chat_conv_insert_own" ON gabriel_chat_conversations;
DROP POLICY IF EXISTS "gabriel_chat_conv_update_own" ON gabriel_chat_conversations;
DROP POLICY IF EXISTS "gabriel_chat_conv_delete_own" ON gabriel_chat_conversations;

CREATE POLICY "gabriel_chat_conv_select_own"
ON gabriel_chat_conversations FOR SELECT
USING (auth.uid()::text = user_id);

CREATE POLICY "gabriel_chat_conv_insert_own"
ON gabriel_chat_conversations FOR INSERT
WITH CHECK (auth.uid()::text = user_id);

CREATE POLICY "gabriel_chat_conv_update_own"
ON gabriel_chat_conversations FOR UPDATE
USING (auth.uid()::text = user_id)
WITH CHECK (auth.uid()::text = user_id);

CREATE POLICY "gabriel_chat_conv_delete_own"
ON gabriel_chat_conversations FOR DELETE
USING (auth.uid()::text = user_id);


-- ══════════════════════════════════════════════════════════════════════════════
-- TABLE : gabriel_chat_messages
-- Messages individuels — is_training_allowed = false par défaut (RGPD)
-- ══════════════════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS gabriel_chat_messages (
    id                  uuid    PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id             text    NOT NULL,
    conversation_id     text,                   -- référence souple vers gabriel_chat_conversations.id
    role                text    NOT NULL,       -- 'user' | 'assistant'
    message_text        text,
    agent               text,
    is_training_allowed boolean DEFAULT false,  -- jamais true sans consentement explicite
    is_redacted         boolean DEFAULT false,
    created_at          timestamptz DEFAULT now(),
    metadata            jsonb   DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_chat_msg_user_id  ON gabriel_chat_messages(user_id);
CREATE INDEX IF NOT EXISTS idx_chat_msg_conv_id  ON gabriel_chat_messages(conversation_id);

ALTER TABLE gabriel_chat_messages ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "gabriel_chat_msg_select_own" ON gabriel_chat_messages;
DROP POLICY IF EXISTS "gabriel_chat_msg_insert_own" ON gabriel_chat_messages;
DROP POLICY IF EXISTS "gabriel_chat_msg_delete_own" ON gabriel_chat_messages;

CREATE POLICY "gabriel_chat_msg_select_own"
ON gabriel_chat_messages FOR SELECT
USING (auth.uid()::text = user_id);

CREATE POLICY "gabriel_chat_msg_insert_own"
ON gabriel_chat_messages FOR INSERT
WITH CHECK (auth.uid()::text = user_id);

CREATE POLICY "gabriel_chat_msg_delete_own"
ON gabriel_chat_messages FOR DELETE
USING (auth.uid()::text = user_id);


-- ══════════════════════════════════════════════════════════════════════════════
-- TABLE : gabriel_training_candidates
-- Candidats à l'amélioration — validation humaine obligatoire avant usage
-- ══════════════════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS gabriel_training_candidates (
    id               uuid    PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id          text,
    source_type      text    NOT NULL,   -- 'survey_response' | 'feedback' | 'chat_approved'
    source_id        text,
    content_summary  text,
    content_hash     text,
    quality_score    integer,
    risk_level       text    DEFAULT 'unknown',   -- 'low' | 'medium' | 'high' | 'unknown'
    anonymized       boolean DEFAULT false,
    approved_for_use boolean DEFAULT false,       -- jamais true automatiquement
    reviewed_by      text,
    created_at       timestamptz DEFAULT now(),
    metadata         jsonb   DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_training_cand_approved ON gabriel_training_candidates(approved_for_use);

ALTER TABLE gabriel_training_candidates ENABLE ROW LEVEL SECURITY;

-- Candidats : lecture seule pour l'utilisateur (admin valide manuellement)
DROP POLICY IF EXISTS "gabriel_training_cand_select_own" ON gabriel_training_candidates;

CREATE POLICY "gabriel_training_cand_select_own"
ON gabriel_training_candidates FOR SELECT
USING (auth.uid()::text = user_id);


-- ══════════════════════════════════════════════════════════════════════════════
-- VÉRIFICATION
-- ══════════════════════════════════════════════════════════════════════════════
-- SELECT tablename, rowsecurity FROM pg_tables
-- WHERE schemaname = 'public' AND tablename LIKE 'gabriel_%'
-- ORDER BY tablename;
