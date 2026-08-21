-- ─── Gabriel V2 — Cross Analyse du Psychologue ──────────────────────────────
--
-- Fondation de persistance multi-source. À exécuter une fois dans le SQL
-- Editor Supabase avant d'activer le lancement Cross Analyse côté frontend.
-- Le script est idempotent et n'altère pas gabriel_analyses : chaque analyse
-- individuelle conserve son cycle de vie et son résultat actuels.
-- ─────────────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS gabriel_cross_analyses (
  id                  uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  cross_analysis_id   text        UNIQUE NOT NULL,
  user_id             text        NOT NULL,
  folder_id           text        DEFAULT '',
  job_id              text        DEFAULT '',
  status              text        NOT NULL DEFAULT 'prepared',
  schema_version      text        NOT NULL DEFAULT '1.0',
  pipeline_version    text        NOT NULL DEFAULT 'cross-v1',
  model_version       text        DEFAULT '',
  embedding_version   text        DEFAULT '',
  source_count        integer     NOT NULL DEFAULT 0,
  result_data         jsonb       NOT NULL DEFAULT '{}'::jsonb,
  error_message       text        DEFAULT '',
  created_at          timestamptz NOT NULL DEFAULT now(),
  updated_at          timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS gabriel_cross_analyses_user_idx
  ON gabriel_cross_analyses (user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS gabriel_cross_analyses_folder_idx
  ON gabriel_cross_analyses (folder_id, created_at DESC);
CREATE INDEX IF NOT EXISTS gabriel_cross_analyses_job_idx
  ON gabriel_cross_analyses (job_id);

ALTER TABLE gabriel_cross_analyses ADD COLUMN IF NOT EXISTS job_id text DEFAULT '';
ALTER TABLE gabriel_cross_analyses ADD COLUMN IF NOT EXISTS pipeline_version text NOT NULL DEFAULT 'cross-v1';
ALTER TABLE gabriel_cross_analyses ADD COLUMN IF NOT EXISTS model_version text DEFAULT '';
ALTER TABLE gabriel_cross_analyses ADD COLUMN IF NOT EXISTS embedding_version text DEFAULT '';
ALTER TABLE gabriel_cross_analyses ADD COLUMN IF NOT EXISTS error_message text DEFAULT '';

-- Une source représente une vidéo dans une session donnée. external_id reste
-- l'identité de plateforme (video_id YouTube), source_id l'identité interne
-- de provenance ; ne jamais les confondre.
CREATE TABLE IF NOT EXISTS gabriel_psychologue_sources (
  id                  uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  source_id           text        UNIQUE NOT NULL,
  user_id             text        NOT NULL,
  platform            text        NOT NULL,
  external_id         text        NOT NULL,
  canonical_url       text        NOT NULL,
  source_metadata     jsonb       NOT NULL DEFAULT '{}'::jsonb,
  created_at          timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS gabriel_psychologue_sources_user_idx
  ON gabriel_psychologue_sources (user_id, platform, external_id);

-- Le lien préserve la position de lecture et relie le résultat historique
-- individuel, sans dupliquer son contenu dans la table Cross.
CREATE TABLE IF NOT EXISTS gabriel_cross_analysis_sources (
  id                  uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  cross_analysis_id   text        NOT NULL,
  source_id           text        NOT NULL,
  user_id             text        NOT NULL,
  analysis_id         text        DEFAULT '',
  position            integer     NOT NULL,
  status              text        NOT NULL DEFAULT 'prepared',
  source_snapshot     jsonb       NOT NULL DEFAULT '{}'::jsonb,
  source_analysis     jsonb       NOT NULL DEFAULT '{}'::jsonb,
  created_at          timestamptz NOT NULL DEFAULT now(),
  UNIQUE (cross_analysis_id, source_id),
  UNIQUE (cross_analysis_id, position)
);

CREATE INDEX IF NOT EXISTS gabriel_cross_analysis_sources_cross_idx
  ON gabriel_cross_analysis_sources (cross_analysis_id, position);
CREATE INDEX IF NOT EXISTS gabriel_cross_analysis_sources_analysis_idx
  ON gabriel_cross_analysis_sources (analysis_id);

ALTER TABLE gabriel_cross_analysis_sources ADD COLUMN IF NOT EXISTS user_id text;
ALTER TABLE gabriel_cross_analysis_sources ADD COLUMN IF NOT EXISTS source_analysis jsonb NOT NULL DEFAULT '{}'::jsonb;

-- La preuve primaire demeure par commentaire et par source. Aucun calcul
-- croisé ne doit persister une version "mélangée" sans source_id/video_id.
CREATE TABLE IF NOT EXISTS gabriel_source_comments (
  id                  uuid        PRIMARY KEY DEFAULT gen_random_uuid(),
  comment_id          text        UNIQUE NOT NULL,
  source_id           text        NOT NULL,
  user_id             text        NOT NULL,
  external_comment_id text        DEFAULT '',
  video_id            text        DEFAULT '',
  text                text        NOT NULL,
  author              text        DEFAULT '',
  likes               integer     NOT NULL DEFAULT 0,
  comment_metadata    jsonb       NOT NULL DEFAULT '{}'::jsonb,
  created_at          timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS gabriel_source_comments_source_idx
  ON gabriel_source_comments (source_id, created_at);
CREATE INDEX IF NOT EXISTS gabriel_source_comments_user_idx
  ON gabriel_source_comments (user_id, source_id);

-- La table folder historique porte un analysis_id simple. La nouvelle colonne
-- est additive : aucune analyse existante ni aucun Stratège ne sont modifiés.
ALTER TABLE gabriel_folders
  ADD COLUMN IF NOT EXISTS cross_analysis_id text DEFAULT '';
CREATE INDEX IF NOT EXISTS gabriel_folders_cross_analysis_idx
  ON gabriel_folders (cross_analysis_id);

-- RLS : même convention que les migrations existantes de Gabriel.
ALTER TABLE gabriel_cross_analyses ENABLE ROW LEVEL SECURITY;
ALTER TABLE gabriel_psychologue_sources ENABLE ROW LEVEL SECURITY;
ALTER TABLE gabriel_cross_analysis_sources ENABLE ROW LEVEL SECURITY;
ALTER TABLE gabriel_source_comments ENABLE ROW LEVEL SECURITY;

DO $$
DECLARE
  table_name text;
  policy_name text;
BEGIN
  FOREACH table_name IN ARRAY ARRAY[
    'gabriel_cross_analyses',
    'gabriel_psychologue_sources',
    'gabriel_cross_analysis_sources',
    'gabriel_source_comments'
  ] LOOP
    policy_name := table_name || '_own_data';
    IF NOT EXISTS (
      SELECT 1 FROM pg_policies
      WHERE schemaname = 'public' AND tablename = table_name AND policyname = policy_name
    ) THEN
      EXECUTE format(
        'CREATE POLICY %I ON %I FOR ALL USING (auth.uid()::text = user_id)',
        policy_name, table_name
      );
    END IF;
  END LOOP;
END $$;

-- Vérification post-migration.
SELECT table_name, column_name, data_type
FROM information_schema.columns
WHERE table_schema = 'public'
  AND table_name IN (
    'gabriel_cross_analyses',
    'gabriel_psychologue_sources',
    'gabriel_cross_analysis_sources',
    'gabriel_source_comments'
  )
ORDER BY table_name, ordinal_position;
