-- ══════════════════════════════════════════════════════════════════════════════
-- GABRIEL — Migration : table gabriel_analysis_jobs
-- ══════════════════════════════════════════════════════════════════════════════
-- Persiste l'état des jobs d'analyse pour survivre aux redémarrages Render.
-- Idempotente : peut être exécutée plusieurs fois sans erreur.
-- NE PAS exécuter sans validation — à copier dans le SQL Editor Supabase.

CREATE TABLE IF NOT EXISTS gabriel_analysis_jobs (
    id            uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id        text UNIQUE NOT NULL,
    user_id       text NOT NULL,            -- TEXT comme les autres tables gabriel_*
    status        text NOT NULL DEFAULT 'pending',
    -- pending | running | completed | failed | interrupted
    progress      integer NOT NULL DEFAULT 0,
    step          text DEFAULT '',
    error_message text DEFAULT '',
    analysis_id   text DEFAULT '',
    result_data   jsonb,
    created_at    timestamptz NOT NULL DEFAULT now(),
    updated_at    timestamptz NOT NULL DEFAULT now(),
    completed_at  timestamptz
);

CREATE INDEX IF NOT EXISTS idx_gabriel_jobs_job_id  ON gabriel_analysis_jobs (job_id);
CREATE INDEX IF NOT EXISTS idx_gabriel_jobs_user_id ON gabriel_analysis_jobs (user_id);
CREATE INDEX IF NOT EXISTS idx_gabriel_jobs_created ON gabriel_analysis_jobs (created_at DESC);

-- ── RLS ───────────────────────────────────────────────────────────────────────
ALTER TABLE gabriel_analysis_jobs ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS "gabriel_jobs_select_own" ON gabriel_analysis_jobs;
CREATE POLICY "gabriel_jobs_select_own"
ON gabriel_analysis_jobs FOR SELECT
USING (auth.uid()::text = user_id);

DROP POLICY IF EXISTS "gabriel_jobs_insert_own" ON gabriel_analysis_jobs;
CREATE POLICY "gabriel_jobs_insert_own"
ON gabriel_analysis_jobs FOR INSERT
WITH CHECK (auth.uid()::text = user_id);

DROP POLICY IF EXISTS "gabriel_jobs_update_own" ON gabriel_analysis_jobs;
CREATE POLICY "gabriel_jobs_update_own"
ON gabriel_analysis_jobs FOR UPDATE
USING (auth.uid()::text = user_id)
WITH CHECK (auth.uid()::text = user_id);

DROP POLICY IF EXISTS "gabriel_jobs_delete_own" ON gabriel_analysis_jobs;
CREATE POLICY "gabriel_jobs_delete_own"
ON gabriel_analysis_jobs FOR DELETE
USING (auth.uid()::text = user_id);

-- NOTE : comme pour les autres tables gabriel_*, l'auth est custom côté backend.
-- Les RLS protègent en dernier recours ; l'isolation principale est le filtre
-- user_id dans chaque requête (api/db.py). Si le backend utilise la clé anon
-- et que auth.uid() est NULL, exécuter en plus (même modèle que gabriel_users) :
--   la clé SERVICE ROLE côté backend uniquement, jamais côté client.

-- ── Nettoyage automatique (optionnel) ─────────────────────────────────────────
-- Les jobs de plus de 7 jours peuvent être purgés par un cron Supabase :
-- DELETE FROM gabriel_analysis_jobs WHERE created_at < now() - interval '7 days';
