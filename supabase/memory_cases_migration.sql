-- ═══════════════════════════════════════════════════════════════════════════
-- MÉMOIRE DE CAS DU STRATÈGE — passage du fichier local à Supabase
--
-- Jusqu'ici, core/memory.py (GabrielMemory) écrivait chaque cas stratégique
-- (audience + décision prise + résultat rapporté) dans un fichier JSON local
-- (data/memory_<user_id>.json). Sur Render, ce disque est effacé à chaque
-- déploiement : tout l'apprentissage stratégique repartait de zéro à chaque
-- mise à jour du code. Cette table le rend permanent.
--
-- Choix de conception : la mémoire est désormais globale (tous les
-- utilisateurs), pas cloisonnée par compte. C'est voulu — voir
-- core/memory.py find_similar() : chaque recherche de cas similaires
-- priorise d'abord les cas du même utilisateur, et ne retombe sur
-- l'ensemble des autres comptes que s'il n'en a pas assez lui-même. Plus
-- d'utilisateurs generate de stratégies, plus les patterns détectés
-- (quelle décision a fonctionné pour quel type d'audience) deviennent
-- fiables pour tout le monde — c'est le comportement d'apprentissage demandé.
--
-- À exécuter dans l'éditeur SQL Supabase. Sans risque : CREATE TABLE IF NOT
-- EXISTS, aucune donnée existante modifiée ni supprimée. Rejouable sans
-- effet de bord.
-- ═══════════════════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS gabriel_memory_cases (
    id                 bigserial PRIMARY KEY,
    case_id            text NOT NULL,
    user_id            uuid NOT NULL,
    case_date          date NOT NULL DEFAULT current_date,
    fingerprint        jsonb NOT NULL DEFAULT '{}'::jsonb,
    audience           jsonb NOT NULL DEFAULT '{}'::jsonb,
    strategie          jsonb NOT NULL DEFAULT '{}'::jsonb,
    contexte_business  jsonb NOT NULL DEFAULT '{}'::jsonb,
    feedback           jsonb,
    satisfaction       jsonb,
    performance        jsonb,
    created_at         timestamptz NOT NULL DEFAULT now(),
    updated_at         timestamptz NOT NULL DEFAULT now()
);

-- Un seul cas par analyse (add_case fait un upsert dessus).
CREATE UNIQUE INDEX IF NOT EXISTS idx_memory_cases_case_id
    ON gabriel_memory_cases (case_id);

-- Deux requêtes faites à chaque génération de stratégie : l'historique
-- complet d'un utilisateur, et un échantillon récent tous comptes confondus.
CREATE INDEX IF NOT EXISTS idx_memory_cases_user
    ON gabriel_memory_cases (user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_memory_cases_recent
    ON gabriel_memory_cases (created_at DESC);

-- Note de sécurité (identique au reste du projet) : la clé Supabase utilisée
-- par cette application est une clé de service, les politiques RLS ne
-- s'appliquent donc pas à ses requêtes. L'isolation par utilisateur vient du
-- filtre `user_id` appliqué explicitement côté Python (voir api/db.py) —
-- sauf ici où le pool global est une lecture intentionnelle, pas une fuite.
