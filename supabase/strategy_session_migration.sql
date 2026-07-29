-- ═══════════════════════════════════════════════════════════════════════════
-- STRATEGY SESSION — Phase 1 (parcours de la Salle de Conseil)
--
-- Ajoute au suivi de session l'étape du PARCOURS (accueil → entretien →
-- conversation → analyse → synthèse → marketing → branding → plan d'action
-- → décision → export), distincte de `current_dimension` qui suit, elle,
-- l'avancement du questionnaire à l'intérieur de l'entretien.
--
-- Les colonnes de contenu sont créées dès maintenant, vides : chaque étape
-- les remplira quand elle sera développée, sans nouvelle migration.
--
-- À exécuter dans l'éditeur SQL Supabase. Sans risque : uniquement des
-- ajouts de colonnes avec valeur par défaut, aucune donnée existante
-- modifiée ni supprimée. Rejouable sans effet de bord (IF NOT EXISTS).
-- ═══════════════════════════════════════════════════════════════════════════

ALTER TABLE gabriel_context_sessions
    ADD COLUMN IF NOT EXISTS current_step text NOT NULL DEFAULT 'welcome';

ALTER TABLE gabriel_context_sessions
    ADD COLUMN IF NOT EXISTS analysis     jsonb NOT NULL DEFAULT '{}'::jsonb,
    ADD COLUMN IF NOT EXISTS marketing    jsonb NOT NULL DEFAULT '{}'::jsonb,
    ADD COLUMN IF NOT EXISTS branding     jsonb NOT NULL DEFAULT '{}'::jsonb,
    ADD COLUMN IF NOT EXISTS action_plan  jsonb NOT NULL DEFAULT '{}'::jsonb,
    ADD COLUMN IF NOT EXISTS decision     jsonb NOT NULL DEFAULT '{}'::jsonb,
    ADD COLUMN IF NOT EXISTS step_history jsonb NOT NULL DEFAULT '[]'::jsonb;

-- Reprise de parcours : retrouver la session active d'un utilisateur est la
-- requête faite à chaque chargement de page.
CREATE INDEX IF NOT EXISTS idx_ctx_sessions_user_step
    ON gabriel_context_sessions (user_id, status, current_step);

-- Note de sécurité (identique au reste du projet) : la clé Supabase utilisée
-- par cette application est une clé de service. Les politiques RLS ne
-- s'appliquent donc pas à ses requêtes. La séparation réelle entre
-- utilisateurs vient du filtre `user_id` appliqué explicitement dans chaque
-- requête Python (voir api/db.py) — jamais de la base seule.
