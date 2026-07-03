-- ─── Gabriel — Migration RLS : colonnes manquantes ───────────────────────────
-- À exécuter dans l'éditeur SQL du dashboard Supabase (une seule fois).
-- Toutes les commandes sont idempotentes (IF NOT EXISTS).

-- ─────────────────────────────────────────────────────────────────────────────
-- TABLE gabriel_analyses
-- Colonnes attendues par Gabriel absentes du schéma initial
-- ─────────────────────────────────────────────────────────────────────────────
ALTER TABLE gabriel_analyses ADD COLUMN IF NOT EXISTS title            TEXT;
ALTER TABLE gabriel_analyses ADD COLUMN IF NOT EXISTS input_data       JSONB;
ALTER TABLE gabriel_analyses ADD COLUMN IF NOT EXISTS result_data      JSONB;
ALTER TABLE gabriel_analyses ADD COLUMN IF NOT EXISTS has_strategy     BOOLEAN DEFAULT FALSE;
ALTER TABLE gabriel_analyses ADD COLUMN IF NOT EXISTS strategy_result  JSONB;
ALTER TABLE gabriel_analyses ADD COLUMN IF NOT EXISTS strategy_id      TEXT;

-- ─────────────────────────────────────────────────────────────────────────────
-- TABLE gabriel_strategies
-- ─────────────────────────────────────────────────────────────────────────────
ALTER TABLE gabriel_strategies ADD COLUMN IF NOT EXISTS business_context JSONB;
ALTER TABLE gabriel_strategies ADD COLUMN IF NOT EXISTS strategy_result  JSONB;

-- ─────────────────────────────────────────────────────────────────────────────
-- TABLE gabriel_feedbacks
-- ─────────────────────────────────────────────────────────────────────────────
ALTER TABLE gabriel_feedbacks ADD COLUMN IF NOT EXISTS was_useful  BOOLEAN;
ALTER TABLE gabriel_feedbacks ADD COLUMN IF NOT EXISTS comment     TEXT;
ALTER TABLE gabriel_feedbacks ADD COLUMN IF NOT EXISTS raw_data    JSONB;

-- ─────────────────────────────────────────────────────────────────────────────
-- TABLE gabriel_exports
-- ─────────────────────────────────────────────────────────────────────────────
ALTER TABLE gabriel_exports ADD COLUMN IF NOT EXISTS pdf_path   TEXT;
ALTER TABLE gabriel_exports ADD COLUMN IF NOT EXISTS full_text  TEXT;

-- ─────────────────────────────────────────────────────────────────────────────
-- Vérification post-migration (exécuter après les ALTER TABLE)
-- ─────────────────────────────────────────────────────────────────────────────
SELECT table_name, column_name, data_type
FROM information_schema.columns
WHERE table_schema = 'public'
  AND table_name IN ('gabriel_analyses','gabriel_strategies','gabriel_feedbacks','gabriel_exports','gabriel_users')
ORDER BY table_name, ordinal_position;
