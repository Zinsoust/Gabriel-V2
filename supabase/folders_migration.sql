-- ─── Gabriel — Migration : Dossiers Stratégiques ─────────────────────────────
--
-- À exécuter UNE FOIS dans le SQL Editor Supabase.
-- Script idempotent (IF NOT EXISTS / DO $$ ... $$).
--
-- Ce que fait ce script :
--   1. Crée la table gabriel_folders
--   2. Active RLS + politique own-data (même pattern que gabriel_analyses)
--   3. Ajoute la colonne folder_id dans gabriel_analyses (nullable)
--   4. Ajoute la colonne folder_id dans gabriel_strategies (nullable)
--   5. Ajoute la colonne folder_id dans gabriel_analysis_jobs (nullable)
-- ─────────────────────────────────────────────────────────────────────────────

-- ═══════════════════════════════════════════════════════════════
-- 1. TABLE gabriel_folders
-- ═══════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS gabriel_folders (
  id              uuid          PRIMARY KEY DEFAULT gen_random_uuid(),
  folder_id       text          UNIQUE NOT NULL,
  user_id         text          NOT NULL,
  title           text          NOT NULL,
  objective       text          DEFAULT '',
  folder_type     text          DEFAULT 'audience',   -- audience|concurrent|offre|avis|campagne|autre
  status          text          DEFAULT 'draft',       -- draft|active|archived
  analysis_id     text          DEFAULT '',
  strategy_id     text          DEFAULT '',
  creator_output_id text        DEFAULT '',
  source_type     text          DEFAULT '',            -- text|youtube|file
  source_summary  text          DEFAULT '',
  step            text          DEFAULT 'source',      -- source|psychologue|stratege|createur|verification
  created_at      timestamptz   DEFAULT now(),
  updated_at      timestamptz   DEFAULT now()
);

-- Index pour les requêtes fréquentes
CREATE INDEX IF NOT EXISTS gabriel_folders_user_idx  ON gabriel_folders (user_id);
CREATE INDEX IF NOT EXISTS gabriel_folders_fid_idx   ON gabriel_folders (folder_id);

-- ═══════════════════════════════════════════════════════════════
-- 2. RLS — Row Level Security
-- ═══════════════════════════════════════════════════════════════

ALTER TABLE gabriel_folders ENABLE ROW LEVEL SECURITY;

DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_policies
    WHERE tablename = 'gabriel_folders' AND policyname = 'folders_own_data'
  ) THEN
    CREATE POLICY folders_own_data ON gabriel_folders
      FOR ALL USING (auth.uid()::text = user_id);
  END IF;
END $$;

-- ═══════════════════════════════════════════════════════════════
-- 3. Colonne folder_id dans gabriel_analyses
-- ═══════════════════════════════════════════════════════════════

DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_name = 'gabriel_analyses' AND column_name = 'folder_id'
  ) THEN
    ALTER TABLE gabriel_analyses ADD COLUMN folder_id text DEFAULT '';
    CREATE INDEX IF NOT EXISTS gabriel_analyses_folder_idx ON gabriel_analyses (folder_id);
  END IF;
END $$;

-- ═══════════════════════════════════════════════════════════════
-- 4. Colonne folder_id dans gabriel_strategies
-- ═══════════════════════════════════════════════════════════════

DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_name = 'gabriel_strategies' AND column_name = 'folder_id'
  ) THEN
    ALTER TABLE gabriel_strategies ADD COLUMN folder_id text DEFAULT '';
    CREATE INDEX IF NOT EXISTS gabriel_strategies_folder_idx ON gabriel_strategies (folder_id);
  END IF;
END $$;

-- ═══════════════════════════════════════════════════════════════
-- 5. Colonne folder_id dans gabriel_analysis_jobs
-- ═══════════════════════════════════════════════════════════════

DO $$ BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_name = 'gabriel_analysis_jobs' AND column_name = 'folder_id'
  ) THEN
    ALTER TABLE gabriel_analysis_jobs ADD COLUMN folder_id text DEFAULT '';
  END IF;
END $$;
