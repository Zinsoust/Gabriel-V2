-- GABRIEL PROSPECT MVP 3 — persistance, déduplication et suivi commercial
-- Version : 2026-10-12
-- Préparée uniquement : NE PAS EXÉCUTER sans validation explicite.
-- Le CSV brut n'est jamais stocké. Les valeurs conservées restent des
-- déclarations importées, non vérifiées indépendamment.

BEGIN;

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS gabriel_prospect_imports (
    import_id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id            text NOT NULL,
    source_filename    text NOT NULL CHECK (char_length(source_filename) <= 255),
    source_sha256      text NOT NULL CHECK (source_sha256 ~ '^[0-9a-f]{64}$'),
    source_size_bytes  integer NOT NULL CHECK (source_size_bytes BETWEEN 0 AND 2097152),
    rows_received      integer NOT NULL CHECK (rows_received BETWEEN 1 AND 1000),
    rows_selected      integer NOT NULL CHECK (rows_selected BETWEEN 1 AND 1000),
    created_at         timestamptz NOT NULL DEFAULT now(),
    retention_until    timestamptz,
    UNIQUE (import_id, user_id)
);

CREATE INDEX IF NOT EXISTS idx_gabriel_prospect_imports_user_created
    ON gabriel_prospect_imports (user_id, created_at DESC);

CREATE TABLE IF NOT EXISTS gabriel_prospects (
    prospect_id        uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id            text NOT NULL,
    import_id          uuid NOT NULL,
    source_row         integer NOT NULL CHECK (source_row BETWEEN 2 AND 1001),
    status             text NOT NULL DEFAULT 'to_enrich' CHECK (status IN (
        'to_enrich', 'qualified', 'contact_ready', 'contacted', 'replied',
        'meeting_scheduled', 'won', 'lost', 'do_not_contact'
    )),
    company_name       text,
    company_domain     text,
    contact_name       text,
    job_title          text,
    agency_type        text,
    email_hash         text CHECK (email_hash IS NULL OR email_hash ~ '^[0-9a-f]{64}$'),
    linkedin_hash      text CHECK (linkedin_hash IS NULL OR linkedin_hash ~ '^[0-9a-f]{64}$'),
    identity_hash      text CHECK (identity_hash IS NULL OR identity_hash ~ '^[0-9a-f]{64}$'),
    icp_score          smallint NOT NULL CHECK (icp_score BETWEEN 0 AND 100),
    data               jsonb NOT NULL DEFAULT '{}'::jsonb,
    facts              jsonb NOT NULL DEFAULT '[]'::jsonb,
    sources            jsonb NOT NULL DEFAULT '[]'::jsonb,
    unknowns           jsonb NOT NULL DEFAULT '[]'::jsonb,
    validation_errors  jsonb NOT NULL DEFAULT '[]'::jsonb,
    score              jsonb NOT NULL DEFAULT '{}'::jsonb,
    eligibility        jsonb NOT NULL DEFAULT '{}'::jsonb,
    CONSTRAINT gabriel_prospect_contact_status_guard CHECK (
        status IN ('to_enrich', 'lost', 'do_not_contact')
        OR COALESCE(
            eligibility ->> 'eligible_for_contact_preparation',
            'false'
        ) = 'true'
    ),
    CONSTRAINT gabriel_prospect_identifier_required CHECK (
        email_hash IS NOT NULL
        OR linkedin_hash IS NOT NULL
        OR identity_hash IS NOT NULL
    ),
    created_at         timestamptz NOT NULL DEFAULT now(),
    updated_at         timestamptz NOT NULL DEFAULT now(),
    do_not_contact_at  timestamptz,
    retention_until    timestamptz,
    UNIQUE (prospect_id, user_id),
    CONSTRAINT gabriel_prospects_import_owner_fk
        FOREIGN KEY (import_id, user_id)
        REFERENCES gabriel_prospect_imports (import_id, user_id)
        ON DELETE RESTRICT
);

-- Un même contact fort ne peut exister qu'une fois par compte. Le domaine
-- d'entreprise n'est volontairement jamais unique : deux contacts d'une même
-- agence restent deux prospects distincts.
CREATE UNIQUE INDEX IF NOT EXISTS uq_gabriel_prospects_user_email
    ON gabriel_prospects (user_id, email_hash)
    WHERE email_hash IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uq_gabriel_prospects_user_linkedin
    ON gabriel_prospects (user_id, linkedin_hash)
    WHERE linkedin_hash IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uq_gabriel_prospects_user_identity
    ON gabriel_prospects (user_id, identity_hash)
    WHERE identity_hash IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_gabriel_prospects_user_status_score
    ON gabriel_prospects (user_id, status, icp_score DESC, updated_at DESC);

CREATE TABLE IF NOT EXISTS gabriel_prospect_events (
    event_id       uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    prospect_id    uuid NOT NULL,
    user_id        text NOT NULL,
    event_type     text NOT NULL CHECK (event_type IN ('created', 'status_changed')),
    from_status    text,
    to_status      text,
    details        jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at     timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT gabriel_prospect_events_owner_fk
        FOREIGN KEY (prospect_id, user_id)
        REFERENCES gabriel_prospects (prospect_id, user_id)
        ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_gabriel_prospect_events_owner_history
    ON gabriel_prospect_events (user_id, prospect_id, created_at DESC);

-- Empreintes pseudonymisées conservées après suppression explicite d'une fiche
-- « ne pas contacter », afin qu'un réimport ne puisse pas réactiver le contact.
CREATE TABLE IF NOT EXISTS gabriel_prospect_suppressions (
    suppression_id   uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id           text NOT NULL,
    identifier_kind   text NOT NULL CHECK (identifier_kind IN ('email', 'linkedin', 'identity')),
    identifier_hash   text NOT NULL CHECK (identifier_hash ~ '^[0-9a-f]{64}$'),
    created_at        timestamptz NOT NULL DEFAULT now(),
    UNIQUE (user_id, identifier_kind, identifier_hash)
);

CREATE INDEX IF NOT EXISTS idx_gabriel_prospect_suppressions_owner
    ON gabriel_prospect_suppressions (user_id, identifier_hash);

-- La vérification applicative améliore le retour utilisateur, mais la base
-- reste l'autorité finale : aucun INSERT direct ne peut réutiliser une
-- empreinte opposée. Le verrou transactionnel par empreinte sérialise ce
-- contrôle avec le BEFORE DELETE qui crée les oppositions.
CREATE OR REPLACE FUNCTION gabriel_prospect_reject_suppressed_insert()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
BEGIN
    PERFORM pg_advisory_xact_lock(
        hashtextextended(
            NEW.user_id || ':' || identifiers.identifier_kind || ':' || identifiers.identifier_hash,
            0
        )
    )
    FROM (VALUES
        ('email', NEW.email_hash),
        ('linkedin', NEW.linkedin_hash),
        ('identity', NEW.identity_hash)
    ) AS identifiers(identifier_kind, identifier_hash)
    WHERE identifiers.identifier_hash IS NOT NULL
    ORDER BY identifiers.identifier_kind, identifiers.identifier_hash;

    IF EXISTS (
        SELECT 1
        FROM public.gabriel_prospect_suppressions AS suppression
        JOIN (VALUES
            ('email', NEW.email_hash),
            ('linkedin', NEW.linkedin_hash),
            ('identity', NEW.identity_hash)
        ) AS identifiers(identifier_kind, identifier_hash)
          ON suppression.identifier_kind = identifiers.identifier_kind
         AND suppression.identifier_hash = identifiers.identifier_hash
        WHERE suppression.user_id = NEW.user_id
          AND identifiers.identifier_hash IS NOT NULL
    ) THEN
        RAISE EXCEPTION USING
            ERRCODE = '23505',
            MESSAGE = 'contact identifier is suppressed';
    END IF;

    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_gabriel_prospect_reject_suppressed_insert ON gabriel_prospects;
CREATE TRIGGER trg_gabriel_prospect_reject_suppressed_insert
BEFORE INSERT ON gabriel_prospects
FOR EACH ROW EXECUTE FUNCTION gabriel_prospect_reject_suppressed_insert();

CREATE OR REPLACE FUNCTION gabriel_prospect_guard_status()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = pg_catalog, public
AS $$
BEGIN
    IF TG_OP = 'UPDATE' THEN
        IF OLD.status = 'do_not_contact' AND NEW.status <> OLD.status THEN
            RAISE EXCEPTION 'do_not_contact status cannot be removed';
        END IF;
        IF NEW.status = 'do_not_contact' AND OLD.status <> NEW.status THEN
            NEW.do_not_contact_at := COALESCE(NEW.do_not_contact_at, now());
        END IF;
    ELSIF NEW.status = 'do_not_contact' THEN
        NEW.do_not_contact_at := COALESCE(NEW.do_not_contact_at, now());
    END IF;
    IF NEW.status NOT IN ('to_enrich', 'lost', 'do_not_contact')
       AND NEW.eligibility ->> 'eligible_for_contact_preparation' IS DISTINCT FROM 'true' THEN
        RAISE EXCEPTION 'contact_not_eligible';
    END IF;
    NEW.updated_at := now();
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_gabriel_prospect_guard_status ON gabriel_prospects;
CREATE TRIGGER trg_gabriel_prospect_guard_status
BEFORE INSERT OR UPDATE ON gabriel_prospects
FOR EACH ROW EXECUTE FUNCTION gabriel_prospect_guard_status();

CREATE OR REPLACE FUNCTION gabriel_prospect_log_change()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
BEGIN
    IF TG_OP = 'INSERT' THEN
        INSERT INTO public.gabriel_prospect_events
            (prospect_id, user_id, event_type, from_status, to_status)
        VALUES (NEW.prospect_id, NEW.user_id, 'created', NULL, NEW.status);
    ELSIF NEW.status IS DISTINCT FROM OLD.status THEN
        INSERT INTO public.gabriel_prospect_events
            (prospect_id, user_id, event_type, from_status, to_status)
        VALUES (NEW.prospect_id, NEW.user_id, 'status_changed', OLD.status, NEW.status);
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_gabriel_prospect_log_change ON gabriel_prospects;
CREATE TRIGGER trg_gabriel_prospect_log_change
AFTER INSERT OR UPDATE OF status ON gabriel_prospects
FOR EACH ROW EXECUTE FUNCTION gabriel_prospect_log_change();

-- La conservation de l'opposition est une garantie de base de données, pas
-- seulement une convention du repository. L'insertion des empreintes et le
-- DELETE appartiennent ainsi à la même transaction PostgreSQL.
CREATE OR REPLACE FUNCTION gabriel_prospect_preserve_suppression()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, public
AS $$
BEGIN
    IF OLD.status <> 'do_not_contact' THEN
        RETURN OLD;
    END IF;

    IF OLD.email_hash IS NULL
       AND OLD.linkedin_hash IS NULL
       AND OLD.identity_hash IS NULL THEN
        RAISE EXCEPTION USING
            ERRCODE = '23514',
            MESSAGE = 'cannot delete do_not_contact without a stable identifier';
    END IF;

    PERFORM pg_advisory_xact_lock(
        hashtextextended(
            OLD.user_id || ':' || identifiers.identifier_kind || ':' || identifiers.identifier_hash,
            0
        )
    )
    FROM (VALUES
        ('email', OLD.email_hash),
        ('linkedin', OLD.linkedin_hash),
        ('identity', OLD.identity_hash)
    ) AS identifiers(identifier_kind, identifier_hash)
    WHERE identifiers.identifier_hash IS NOT NULL
    ORDER BY identifiers.identifier_kind, identifiers.identifier_hash;

    INSERT INTO public.gabriel_prospect_suppressions
        (user_id, identifier_kind, identifier_hash)
    SELECT OLD.user_id, identifiers.identifier_kind, identifiers.identifier_hash
    FROM (VALUES
        ('email', OLD.email_hash),
        ('linkedin', OLD.linkedin_hash),
        ('identity', OLD.identity_hash)
    ) AS identifiers(identifier_kind, identifier_hash)
    WHERE identifiers.identifier_hash IS NOT NULL
    ON CONFLICT (user_id, identifier_kind, identifier_hash) DO NOTHING;

    RETURN OLD;
END;
$$;

DROP TRIGGER IF EXISTS trg_gabriel_prospect_preserve_suppression ON gabriel_prospects;
CREATE TRIGGER trg_gabriel_prospect_preserve_suppression
BEFORE DELETE ON gabriel_prospects
FOR EACH ROW EXECUTE FUNCTION gabriel_prospect_preserve_suppression();

-- RLS stricte. Avec l'authentification custom actuelle, le backend doit utiliser
-- une clé serveur gardée hors du navigateur et appliquer user_id à chaque requête.
-- Une clé anon sans JWT Supabase sera refusée par ces politiques.
ALTER TABLE gabriel_prospect_imports ENABLE ROW LEVEL SECURITY;
ALTER TABLE gabriel_prospect_imports FORCE ROW LEVEL SECURITY;
ALTER TABLE gabriel_prospects ENABLE ROW LEVEL SECURITY;
ALTER TABLE gabriel_prospects FORCE ROW LEVEL SECURITY;
ALTER TABLE gabriel_prospect_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE gabriel_prospect_events FORCE ROW LEVEL SECURITY;
ALTER TABLE gabriel_prospect_suppressions ENABLE ROW LEVEL SECURITY;
ALTER TABLE gabriel_prospect_suppressions FORCE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS gabriel_prospect_imports_select_own ON gabriel_prospect_imports;
CREATE POLICY gabriel_prospect_imports_select_own ON gabriel_prospect_imports
    FOR SELECT USING (auth.uid()::text = user_id);
DROP POLICY IF EXISTS gabriel_prospect_imports_insert_own ON gabriel_prospect_imports;
CREATE POLICY gabriel_prospect_imports_insert_own ON gabriel_prospect_imports
    FOR INSERT WITH CHECK (auth.uid()::text = user_id);
DROP POLICY IF EXISTS gabriel_prospect_imports_delete_own ON gabriel_prospect_imports;
CREATE POLICY gabriel_prospect_imports_delete_own ON gabriel_prospect_imports
    FOR DELETE USING (auth.uid()::text = user_id);

DROP POLICY IF EXISTS gabriel_prospects_select_own ON gabriel_prospects;
CREATE POLICY gabriel_prospects_select_own ON gabriel_prospects
    FOR SELECT USING (auth.uid()::text = user_id);
DROP POLICY IF EXISTS gabriel_prospects_insert_own ON gabriel_prospects;
CREATE POLICY gabriel_prospects_insert_own ON gabriel_prospects
    FOR INSERT WITH CHECK (auth.uid()::text = user_id);
DROP POLICY IF EXISTS gabriel_prospects_update_own ON gabriel_prospects;
CREATE POLICY gabriel_prospects_update_own ON gabriel_prospects
    FOR UPDATE USING (auth.uid()::text = user_id)
    WITH CHECK (auth.uid()::text = user_id);
DROP POLICY IF EXISTS gabriel_prospects_delete_own ON gabriel_prospects;
CREATE POLICY gabriel_prospects_delete_own ON gabriel_prospects
    FOR DELETE USING (auth.uid()::text = user_id);

DROP POLICY IF EXISTS gabriel_prospect_events_select_own ON gabriel_prospect_events;
CREATE POLICY gabriel_prospect_events_select_own ON gabriel_prospect_events
    FOR SELECT USING (auth.uid()::text = user_id);

DROP POLICY IF EXISTS gabriel_prospect_suppressions_select_own ON gabriel_prospect_suppressions;
CREATE POLICY gabriel_prospect_suppressions_select_own ON gabriel_prospect_suppressions
    FOR SELECT USING (auth.uid()::text = user_id);
DROP POLICY IF EXISTS gabriel_prospect_suppressions_insert_own ON gabriel_prospect_suppressions;

-- Accès Data API explicite : aucun accès navigateur direct. Le backend Flask
-- est le seul consommateur et sa clé service_role doit rester côté serveur.
REVOKE ALL ON TABLE
    gabriel_prospect_imports,
    gabriel_prospects,
    gabriel_prospect_events,
    gabriel_prospect_suppressions
FROM PUBLIC, anon, authenticated, service_role;

GRANT USAGE ON SCHEMA public TO service_role;
GRANT SELECT, INSERT, DELETE ON TABLE gabriel_prospect_imports TO service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE gabriel_prospects TO service_role;
GRANT SELECT ON TABLE gabriel_prospect_events TO service_role;
GRANT SELECT ON TABLE gabriel_prospect_suppressions TO service_role;

-- Les fonctions ne sont jamais des RPC publiques. Les triggers, créés par le
-- propriétaire de la migration, continuent à les exécuter sans droit EXECUTE
-- accordé aux rôles PostgREST. Les UUID évitent toute séquence à autoriser.
REVOKE ALL ON FUNCTION public.gabriel_prospect_guard_status()
    FROM PUBLIC, anon, authenticated, service_role;
REVOKE ALL ON FUNCTION public.gabriel_prospect_log_change()
    FROM PUBLIC, anon, authenticated, service_role;
REVOKE ALL ON FUNCTION public.gabriel_prospect_preserve_suppression()
    FROM PUBLIC, anon, authenticated, service_role;
REVOKE ALL ON FUNCTION public.gabriel_prospect_reject_suppressed_insert()
    FROM PUBLIC, anon, authenticated, service_role;

-- Conservation : retention_until reste NULL tant que la durée métier n'est pas
-- validée. La suppression explicite d'un prospect efface son historique par
-- cascade. Un futur job de purge pourra supprimer les lignes arrivées à échéance :
-- DELETE FROM gabriel_prospects WHERE retention_until < now();

COMMIT;
