-- Gabriel private beta: backend-only Supabase access.
--
-- Gabriel currently authenticates users in the Flask application. Its UUIDs
-- are not Supabase Auth UUIDs, so auth.uid()-based policies cannot be the
-- authority for this beta. Browser roles must have no direct data or RPC
-- access; the server is the only database client and always derives user_id
-- from its signed session.

BEGIN;

SET LOCAL search_path = pg_catalog, pg_temp;

DO $gabriel$
DECLARE
    v_role text;
    v_table text;
    v_missing text[];
    v_object record;
    v_required_tables constant text[] := ARRAY[
        'gabriel_users',
        'gabriel_analyses',
        'gabriel_strategies',
        'gabriel_feedbacks',
        'gabriel_exports',
        'gabriel_survey_events',
        'gabriel_survey_responses',
        'gabriel_consent_records',
        'gabriel_chat_conversations',
        'gabriel_chat_messages',
        'gabriel_training_candidates',
        'gabriel_folders',
        'gabriel_context_sessions',
        'gabriel_context_messages',
        'gabriel_context_fields',
        'gabriel_memory_cases',
        'gabriel_ux_settings',
        'gabriel_cross_analyses',
        'gabriel_psychologue_sources',
        'gabriel_cross_analysis_sources',
        'gabriel_source_comments',
        'gabriel_analysis_jobs',
        'gabriel_credit_accounts',
        'gabriel_credit_grants',
        'gabriel_credit_legacy_snapshots',
        'gabriel_credit_reservations',
        'gabriel_credit_allocations',
        'gabriel_credit_provider_usage',
        'gabriel_credit_ledger',
        'gabriel_provider_budget_policies',
        'gabriel_provider_budget_policy_events',
        'gabriel_provider_budget_periods',
        'gabriel_provider_budget_attempts'
    ];
BEGIN
    FOREACH v_role IN ARRAY ARRAY['anon', 'authenticated', 'service_role'] LOOP
        IF NOT EXISTS (SELECT 1 FROM pg_catalog.pg_roles WHERE rolname = v_role) THEN
            RAISE EXCEPTION 'required Supabase role missing: %', v_role
                USING ERRCODE = '42704';
        END IF;
    END LOOP;

    SELECT pg_catalog.array_agg(required_name ORDER BY required_name)
      INTO v_missing
      FROM pg_catalog.unnest(v_required_tables) AS required_table(required_name)
     WHERE pg_catalog.to_regclass('public.' || required_name) IS NULL;

    IF v_missing IS NOT NULL THEN
        RAISE EXCEPTION 'required Gabriel tables missing: %', v_missing
            USING ERRCODE = '42P01';
    END IF;

    -- RLS remains a second barrier. Direct browser roles are denied at the
    -- privilege layer because their auth.uid() cannot represent Gabriel's
    -- current application UUIDs.
    FOR v_object IN
        SELECT c.relname
          FROM pg_catalog.pg_class AS c
          JOIN pg_catalog.pg_namespace AS n ON n.oid = c.relnamespace
         WHERE n.nspname = 'public'
           AND c.relkind IN ('r', 'p')
           AND c.relname LIKE 'gabriel\_%' ESCAPE '\'
    LOOP
        EXECUTE pg_catalog.format(
            'ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY', v_object.relname
        );
        EXECUTE pg_catalog.format(
            'REVOKE ALL PRIVILEGES ON TABLE public.%I FROM PUBLIC, anon, authenticated',
            v_object.relname
        );
    END LOOP;

    FOR v_object IN
        SELECT c.relname
          FROM pg_catalog.pg_class AS c
          JOIN pg_catalog.pg_namespace AS n ON n.oid = c.relnamespace
         WHERE n.nspname = 'public'
           AND c.relkind = 'S'
           AND c.relname LIKE 'gabriel\_%' ESCAPE '\'
    LOOP
        EXECUTE pg_catalog.format(
            'REVOKE ALL PRIVILEGES ON SEQUENCE public.%I FROM PUBLIC, anon, authenticated',
            v_object.relname
        );
    END LOOP;

    FOR v_object IN
        SELECT p.oid::pg_catalog.regprocedure AS signature
          FROM pg_catalog.pg_proc AS p
          JOIN pg_catalog.pg_namespace AS n ON n.oid = p.pronamespace
         WHERE n.nspname = 'public'
           AND p.proname LIKE 'gabriel\_%' ESCAPE '\'
    LOOP
        EXECUTE pg_catalog.format(
            'REVOKE ALL PRIVILEGES ON FUNCTION %s FROM PUBLIC, anon, authenticated',
            v_object.signature
        );
    END LOOP;
END;
$gabriel$;

COMMIT;
