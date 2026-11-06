-- Gabriel V3 - authoritative persistent provider budgets
-- Additive migration. Requires 20261024_credit_ledger_phase1.sql and
-- 20261026_credit_ledger_expiration_fix.sql. Never runs automatically.
-- The application supplies only a conservative maximum cost. PostgreSQL owns
-- the active policy, UTC period boundaries and both user/global limits.

BEGIN;

CREATE TABLE public.gabriel_provider_budget_policies (
    policy_id uuid PRIMARY KEY DEFAULT pg_catalog.gen_random_uuid(),
    provider text NOT NULL UNIQUE,
    policy_version text NOT NULL,
    period_kind text NOT NULL CHECK (period_kind IN ('day', 'month')),
    user_limit_micros bigint NOT NULL CHECK (user_limit_micros > 0),
    global_limit_micros bigint NOT NULL CHECK (global_limit_micros > 0),
    enabled boolean NOT NULL DEFAULT false,
    effective_from timestamptz NOT NULL,
    effective_until timestamptz,
    created_at timestamptz NOT NULL DEFAULT pg_catalog.clock_timestamp(),
    updated_at timestamptz NOT NULL DEFAULT pg_catalog.clock_timestamp(),
    CHECK (provider = pg_catalog.lower(pg_catalog.btrim(provider)) AND provider <> ''),
    CHECK (policy_version = pg_catalog.btrim(policy_version) AND policy_version <> ''),
    CHECK (user_limit_micros <= global_limit_micros),
    CHECK (effective_until IS NULL OR effective_until > effective_from)
);

CREATE TABLE public.gabriel_provider_budget_policy_events (
    policy_event_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    provider text NOT NULL,
    event_type text NOT NULL CHECK (event_type IN ('provisioned', 'disabled')),
    previous_policy jsonb,
    resulting_policy jsonb NOT NULL,
    occurred_at timestamptz NOT NULL DEFAULT pg_catalog.clock_timestamp()
);

CREATE TABLE public.gabriel_provider_budget_periods (
    budget_id uuid PRIMARY KEY DEFAULT pg_catalog.gen_random_uuid(),
    policy_id uuid NOT NULL REFERENCES public.gabriel_provider_budget_policies(policy_id),
    policy_version text NOT NULL,
    provider text NOT NULL,
    period_kind text NOT NULL CHECK (period_kind IN ('day', 'month')),
    scope_type text NOT NULL CHECK (scope_type IN ('global', 'user')),
    scope_key text NOT NULL,
    period_start timestamptz NOT NULL,
    period_end timestamptz NOT NULL,
    limit_micros bigint NOT NULL CHECK (limit_micros > 0),
    reserved_micros bigint NOT NULL DEFAULT 0 CHECK (reserved_micros >= 0),
    settled_micros bigint NOT NULL DEFAULT 0 CHECK (settled_micros >= 0),
    uncertain_micros bigint NOT NULL DEFAULT 0 CHECK (uncertain_micros >= 0),
    created_at timestamptz NOT NULL DEFAULT pg_catalog.clock_timestamp(),
    updated_at timestamptz NOT NULL DEFAULT pg_catalog.clock_timestamp(),
    UNIQUE (provider, scope_type, scope_key, period_start),
    CHECK (provider = pg_catalog.lower(pg_catalog.btrim(provider)) AND provider <> ''),
    CHECK (scope_key <> ''),
    CHECK ((scope_type = 'global' AND scope_key = 'global') OR scope_type = 'user'),
    CHECK (period_end > period_start),
    CHECK (reserved_micros + settled_micros + uncertain_micros <= limit_micros)
);

CREATE TABLE public.gabriel_provider_budget_attempts (
    budget_attempt_id uuid PRIMARY KEY DEFAULT pg_catalog.gen_random_uuid(),
    reservation_id uuid NOT NULL REFERENCES public.gabriel_credit_reservations(reservation_id),
    attempt_no integer NOT NULL CHECK (attempt_no > 0),
    user_id text NOT NULL,
    provider text NOT NULL,
    model text NOT NULL,
    policy_id uuid NOT NULL REFERENCES public.gabriel_provider_budget_policies(policy_id),
    policy_version text NOT NULL,
    period_kind text NOT NULL CHECK (period_kind IN ('day', 'month')),
    period_start timestamptz NOT NULL,
    period_end timestamptz NOT NULL,
    global_budget_id uuid NOT NULL REFERENCES public.gabriel_provider_budget_periods(budget_id),
    user_budget_id uuid NOT NULL REFERENCES public.gabriel_provider_budget_periods(budget_id),
    max_cost_micros bigint NOT NULL CHECK (max_cost_micros > 0),
    actual_cost_micros bigint CHECK (
        actual_cost_micros IS NULL OR
        (actual_cost_micros >= 0 AND actual_cost_micros <= max_cost_micros)
    ),
    state text NOT NULL DEFAULT 'reserved'
        CHECK (state IN ('reserved', 'succeeded', 'failed', 'uncertain')),
    created_at timestamptz NOT NULL DEFAULT pg_catalog.clock_timestamp(),
    updated_at timestamptz NOT NULL DEFAULT pg_catalog.clock_timestamp(),
    UNIQUE (reservation_id, attempt_no),
    CHECK (provider = pg_catalog.lower(pg_catalog.btrim(provider)) AND provider <> ''),
    CHECK (model = pg_catalog.btrim(model) AND model <> ''),
    CHECK (period_end > period_start),
    CHECK (global_budget_id <> user_budget_id)
);

CREATE INDEX gabriel_provider_budget_attempts_user_period_idx
    ON public.gabriel_provider_budget_attempts (user_id, provider, period_start);

ALTER TABLE public.gabriel_provider_budget_policies ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.gabriel_provider_budget_policy_events ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.gabriel_provider_budget_periods ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.gabriel_provider_budget_attempts ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON TABLE public.gabriel_provider_budget_policies FROM PUBLIC, anon, authenticated, service_role;
REVOKE ALL ON TABLE public.gabriel_provider_budget_policy_events FROM PUBLIC, anon, authenticated, service_role;
REVOKE ALL ON TABLE public.gabriel_provider_budget_periods FROM PUBLIC, anon, authenticated, service_role;
REVOKE ALL ON TABLE public.gabriel_provider_budget_attempts FROM PUBLIC, anon, authenticated, service_role;
REVOKE ALL ON SEQUENCE public.gabriel_provider_budget_policy_events_policy_event_id_seq
    FROM PUBLIC, anon, authenticated, service_role;

CREATE TRIGGER gabriel_provider_budget_policy_events_immutable
BEFORE UPDATE OR DELETE ON public.gabriel_provider_budget_policy_events
FOR EACH ROW EXECUTE FUNCTION public.gabriel_credit_ledger_immutable();

-- Separate administrative operation. No runtime role receives EXECUTE.
CREATE OR REPLACE FUNCTION public.gabriel_provider_budget_admin_set_policy(
    p_provider text,
    p_policy_version text,
    p_period_kind text,
    p_user_limit_micros bigint,
    p_global_limit_micros bigint,
    p_enabled boolean,
    p_effective_from timestamptz,
    p_effective_until timestamptz
) RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
    v_provider text := pg_catalog.lower(pg_catalog.btrim(p_provider));
    v_existing public.gabriel_provider_budget_policies%ROWTYPE;
    v_result public.gabriel_provider_budget_policies%ROWTYPE;
    v_now timestamptz := pg_catalog.clock_timestamp();
    v_material_change boolean;
BEGIN
    IF v_provider IS NULL OR v_provider = '' OR p_provider IS DISTINCT FROM v_provider
       OR nullif(pg_catalog.btrim(p_policy_version), '') IS NULL
       OR p_policy_version IS DISTINCT FROM pg_catalog.btrim(p_policy_version)
       OR p_period_kind NOT IN ('day', 'month')
       OR p_user_limit_micros IS NULL OR p_global_limit_micros IS NULL
       OR p_user_limit_micros <= 0 OR p_global_limit_micros <= 0
       OR p_user_limit_micros > p_global_limit_micros
       OR p_enabled IS NULL OR p_effective_from IS NULL
       OR (p_effective_until IS NOT NULL AND p_effective_until <= p_effective_from) THEN
        RAISE EXCEPTION 'invalid provider budget policy' USING ERRCODE = '22023';
    END IF;

    SELECT * INTO v_existing
      FROM public.gabriel_provider_budget_policies
     WHERE provider = v_provider
     FOR UPDATE;

    IF FOUND THEN
        v_material_change :=
            v_existing.policy_version IS DISTINCT FROM p_policy_version
            OR v_existing.period_kind IS DISTINCT FROM p_period_kind
            OR v_existing.user_limit_micros IS DISTINCT FROM p_user_limit_micros
            OR v_existing.global_limit_micros IS DISTINCT FROM p_global_limit_micros
            OR v_existing.effective_from IS DISTINCT FROM p_effective_from
            OR v_existing.effective_until IS DISTINCT FROM p_effective_until;
        IF v_material_change AND EXISTS (
            SELECT 1 FROM public.gabriel_provider_budget_periods
             WHERE provider = v_provider
               AND period_start <= v_now AND period_end > v_now
        ) THEN
            RAISE EXCEPTION 'provider budget policy cannot change inside an active period'
                USING ERRCODE = 'P0001';
        END IF;
    END IF;

    INSERT INTO public.gabriel_provider_budget_policies (
        provider, policy_version, period_kind,
        user_limit_micros, global_limit_micros, enabled,
        effective_from, effective_until
    ) VALUES (
        v_provider, p_policy_version, p_period_kind,
        p_user_limit_micros, p_global_limit_micros, p_enabled,
        p_effective_from, p_effective_until
    )
    ON CONFLICT (provider) DO UPDATE SET
        policy_version = EXCLUDED.policy_version,
        period_kind = EXCLUDED.period_kind,
        user_limit_micros = EXCLUDED.user_limit_micros,
        global_limit_micros = EXCLUDED.global_limit_micros,
        enabled = EXCLUDED.enabled,
        effective_from = EXCLUDED.effective_from,
        effective_until = EXCLUDED.effective_until,
        updated_at = pg_catalog.clock_timestamp()
    RETURNING * INTO v_result;

    INSERT INTO public.gabriel_provider_budget_policy_events (
        provider, event_type, previous_policy, resulting_policy
    ) VALUES (
        v_provider,
        CASE WHEN p_enabled THEN 'provisioned' ELSE 'disabled' END,
        CASE WHEN v_existing.policy_id IS NULL THEN NULL ELSE pg_catalog.to_jsonb(v_existing) END,
        pg_catalog.to_jsonb(v_result)
    );
    RETURN pg_catalog.to_jsonb(v_result);
END;
$$;

-- Internal helper. Every policy value comes from a locked PostgreSQL row.
CREATE OR REPLACE FUNCTION public.gabriel_provider_budget_lock_period(
    p_policy_id uuid,
    p_policy_version text,
    p_provider text,
    p_period_kind text,
    p_scope_type text,
    p_scope_key text,
    p_period_start timestamptz,
    p_period_end timestamptz,
    p_limit_micros bigint
) RETURNS public.gabriel_provider_budget_periods
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
    v_period public.gabriel_provider_budget_periods%ROWTYPE;
BEGIN
    IF p_policy_id IS NULL
       OR nullif(pg_catalog.btrim(p_policy_version), '') IS NULL
       OR nullif(pg_catalog.btrim(p_provider), '') IS NULL
       OR p_provider IS DISTINCT FROM pg_catalog.lower(pg_catalog.btrim(p_provider))
       OR p_period_kind NOT IN ('day', 'month')
       OR p_scope_type NOT IN ('global', 'user')
       OR nullif(pg_catalog.btrim(p_scope_key), '') IS NULL
       OR (p_scope_type = 'global' AND p_scope_key <> 'global')
       OR p_period_start IS NULL OR p_period_end <= p_period_start
       OR p_limit_micros IS NULL OR p_limit_micros <= 0 THEN
        RAISE EXCEPTION 'invalid provider budget period' USING ERRCODE = '22023';
    END IF;
    IF (p_period_kind = 'day' AND (
            p_period_start IS DISTINCT FROM
                (pg_catalog.date_trunc('day', p_period_start AT TIME ZONE 'UTC') AT TIME ZONE 'UTC')
            OR p_period_end IS DISTINCT FROM p_period_start + interval '1 day'
        )) OR (p_period_kind = 'month' AND (
            p_period_start IS DISTINCT FROM
                (pg_catalog.date_trunc('month', p_period_start AT TIME ZONE 'UTC') AT TIME ZONE 'UTC')
            OR p_period_end IS DISTINCT FROM p_period_start + interval '1 month'
        )) THEN
        RAISE EXCEPTION 'non-canonical provider budget period' USING ERRCODE = '22023';
    END IF;

    INSERT INTO public.gabriel_provider_budget_periods (
        policy_id, policy_version, provider, period_kind,
        scope_type, scope_key, period_start, period_end, limit_micros
    ) VALUES (
        p_policy_id, p_policy_version, p_provider, p_period_kind,
        p_scope_type, p_scope_key, p_period_start, p_period_end, p_limit_micros
    ) ON CONFLICT (provider, scope_type, scope_key, period_start) DO NOTHING;

    SELECT * INTO v_period
      FROM public.gabriel_provider_budget_periods
     WHERE provider = p_provider
       AND scope_type = p_scope_type
       AND scope_key = p_scope_key
       AND period_start = p_period_start
     FOR UPDATE;

    IF v_period.policy_id IS DISTINCT FROM p_policy_id
       OR v_period.policy_version IS DISTINCT FROM p_policy_version
       OR v_period.period_kind IS DISTINCT FROM p_period_kind
       OR v_period.period_end IS DISTINCT FROM p_period_end
       OR v_period.limit_micros <> p_limit_micros THEN
        RAISE EXCEPTION 'provider budget policy changed inside an active period'
            USING ERRCODE = 'P0001';
    END IF;
    RETURN v_period;
END;
$$;

CREATE OR REPLACE FUNCTION public.gabriel_provider_budget_reserve_attempt(
    p_authenticated_user_id text,
    p_user_id text,
    p_reservation_id uuid,
    p_attempt_no integer,
    p_provider text,
    p_model text,
    p_max_cost_micros bigint,
    p_provider_request_id text
) RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
    v_provider text := pg_catalog.lower(pg_catalog.btrim(p_provider));
    v_now timestamptz := pg_catalog.clock_timestamp();
    v_period_start timestamptz;
    v_period_end timestamptz;
    v_policy public.gabriel_provider_budget_policies%ROWTYPE;
    v_existing public.gabriel_provider_budget_attempts%ROWTYPE;
    v_global public.gabriel_provider_budget_periods%ROWTYPE;
    v_user public.gabriel_provider_budget_periods%ROWTYPE;
    v_attempt public.gabriel_provider_budget_attempts%ROWTYPE;
BEGIN
    PERFORM public.gabriel_credit_assert_actor(p_authenticated_user_id, p_user_id);
    IF p_attempt_no IS NULL OR p_max_cost_micros IS NULL
       OR p_attempt_no <= 0 OR p_max_cost_micros <= 0
       OR v_provider IS NULL OR v_provider = '' OR p_provider IS DISTINCT FROM v_provider
       OR nullif(pg_catalog.btrim(p_model), '') IS NULL
       OR p_model IS DISTINCT FROM pg_catalog.btrim(p_model) THEN
        RAISE EXCEPTION 'invalid provider attempt' USING ERRCODE = '22023';
    END IF;

    PERFORM public.gabriel_credit_record_provider_attempt(
        p_authenticated_user_id, p_user_id, p_reservation_id, p_attempt_no,
        v_provider, p_model, p_max_cost_micros, p_provider_request_id
    );

    SELECT * INTO v_existing
      FROM public.gabriel_provider_budget_attempts
     WHERE reservation_id = p_reservation_id AND attempt_no = p_attempt_no;
    IF FOUND THEN
        IF v_existing.user_id <> p_user_id
           OR v_existing.provider <> v_provider
           OR v_existing.model <> p_model
           OR v_existing.max_cost_micros <> p_max_cost_micros THEN
            RAISE EXCEPTION 'provider budget attempt idempotency conflict'
                USING ERRCODE = 'P0001';
        END IF;
        RETURN pg_catalog.to_jsonb(v_existing)
            || pg_catalog.jsonb_build_object('idempotent', true);
    END IF;

    SELECT * INTO v_policy
      FROM public.gabriel_provider_budget_policies
     WHERE provider = v_provider
       AND enabled
       AND effective_from <= v_now
       AND (effective_until IS NULL OR effective_until > v_now)
     FOR SHARE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'provider budget policy unavailable' USING ERRCODE = 'P0001';
    END IF;

    IF v_policy.period_kind = 'day' THEN
        v_period_start := pg_catalog.date_trunc('day', v_now AT TIME ZONE 'UTC') AT TIME ZONE 'UTC';
        v_period_end := v_period_start + interval '1 day';
    ELSIF v_policy.period_kind = 'month' THEN
        v_period_start := pg_catalog.date_trunc('month', v_now AT TIME ZONE 'UTC') AT TIME ZONE 'UTC';
        v_period_end := v_period_start + interval '1 month';
    ELSE
        RAISE EXCEPTION 'invalid stored provider budget policy' USING ERRCODE = 'P0001';
    END IF;

    -- Stable lock order: credit reservation -> policy -> global -> user.
    v_global := public.gabriel_provider_budget_lock_period(
        v_policy.policy_id, v_policy.policy_version, v_provider,
        v_policy.period_kind, 'global', 'global',
        v_period_start, v_period_end, v_policy.global_limit_micros
    );
    v_user := public.gabriel_provider_budget_lock_period(
        v_policy.policy_id, v_policy.policy_version, v_provider,
        v_policy.period_kind, 'user', p_user_id,
        v_period_start, v_period_end, v_policy.user_limit_micros
    );
    IF v_global.reserved_micros + v_global.settled_micros
       + v_global.uncertain_micros + p_max_cost_micros > v_global.limit_micros THEN
        RAISE EXCEPTION 'global provider budget exceeded' USING ERRCODE = 'P0001';
    END IF;
    IF v_user.reserved_micros + v_user.settled_micros
       + v_user.uncertain_micros + p_max_cost_micros > v_user.limit_micros THEN
        RAISE EXCEPTION 'user provider budget exceeded' USING ERRCODE = 'P0001';
    END IF;

    INSERT INTO public.gabriel_provider_budget_attempts (
        reservation_id, attempt_no, user_id, provider, model,
        policy_id, policy_version, period_kind, period_start, period_end,
        global_budget_id, user_budget_id, max_cost_micros
    ) VALUES (
        p_reservation_id, p_attempt_no, p_user_id, v_provider, p_model,
        v_policy.policy_id, v_policy.policy_version, v_policy.period_kind,
        v_period_start, v_period_end, v_global.budget_id, v_user.budget_id,
        p_max_cost_micros
    ) RETURNING * INTO v_attempt;

    UPDATE public.gabriel_provider_budget_periods
       SET reserved_micros = reserved_micros + p_max_cost_micros,
           updated_at = pg_catalog.clock_timestamp()
     WHERE budget_id IN (v_global.budget_id, v_user.budget_id);
    RETURN pg_catalog.to_jsonb(v_attempt)
        || pg_catalog.jsonb_build_object('idempotent', false);
END;
$$;

CREATE OR REPLACE FUNCTION public.gabriel_provider_budget_settle_attempt(
    p_authenticated_user_id text,
    p_user_id text,
    p_reservation_id uuid,
    p_attempt_no integer,
    p_state text,
    p_actual_cost_micros bigint,
    p_input_tokens bigint,
    p_output_tokens bigint
) RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
    v_attempt public.gabriel_provider_budget_attempts%ROWTYPE;
    v_actual bigint;
    v_global public.gabriel_provider_budget_periods%ROWTYPE;
    v_user public.gabriel_provider_budget_periods%ROWTYPE;
    v_reconcile_uncertain boolean := false;
    v_updated integer;
BEGIN
    PERFORM public.gabriel_credit_assert_actor(p_authenticated_user_id, p_user_id);
    IF p_state IS NULL OR p_state NOT IN ('succeeded', 'failed', 'uncertain') THEN
        RAISE EXCEPTION 'invalid provider budget settlement state' USING ERRCODE = '22023';
    END IF;

    PERFORM public.gabriel_credit_settle_provider_attempt(
        p_authenticated_user_id, p_user_id, p_reservation_id, p_attempt_no,
        p_state, p_actual_cost_micros, p_input_tokens, p_output_tokens
    );
    SELECT * INTO v_attempt
      FROM public.gabriel_provider_budget_attempts
     WHERE reservation_id = p_reservation_id AND attempt_no = p_attempt_no
     FOR UPDATE;
    IF NOT FOUND OR v_attempt.user_id <> p_user_id THEN
        RAISE EXCEPTION 'provider budget attempt not found' USING ERRCODE = 'P0001';
    END IF;
    IF v_attempt.state <> 'reserved' THEN
        IF v_attempt.state = 'uncertain'
           AND p_state IN ('succeeded', 'failed')
           AND p_actual_cost_micros IS NOT NULL THEN
            v_reconcile_uncertain := true;
        ELSIF v_attempt.state <> p_state
           OR v_attempt.actual_cost_micros IS DISTINCT FROM p_actual_cost_micros THEN
            RAISE EXCEPTION 'provider budget settlement idempotency conflict'
                USING ERRCODE = 'P0001';
        ELSE
            RETURN pg_catalog.to_jsonb(v_attempt)
                || pg_catalog.jsonb_build_object('idempotent', true);
        END IF;
    END IF;

    SELECT * INTO v_global FROM public.gabriel_provider_budget_periods
     WHERE budget_id = v_attempt.global_budget_id FOR UPDATE;
    SELECT * INTO v_user FROM public.gabriel_provider_budget_periods
     WHERE budget_id = v_attempt.user_budget_id FOR UPDATE;
    IF v_global.budget_id IS NULL OR v_user.budget_id IS NULL
       OR v_global.policy_id <> v_attempt.policy_id
       OR v_user.policy_id <> v_attempt.policy_id
       OR v_global.policy_version <> v_attempt.policy_version
       OR v_user.policy_version <> v_attempt.policy_version
       OR v_global.provider <> v_attempt.provider
       OR v_user.provider <> v_attempt.provider
       OR v_global.scope_type <> 'global' OR v_global.scope_key <> 'global'
       OR v_user.scope_type <> 'user' OR v_user.scope_key <> p_user_id
       OR v_global.period_start <> v_attempt.period_start
       OR v_user.period_start <> v_attempt.period_start THEN
        RAISE EXCEPTION 'provider budget period integrity failure' USING ERRCODE = 'P0001';
    END IF;

    IF v_reconcile_uncertain THEN
        IF p_actual_cost_micros < 0 OR p_actual_cost_micros > v_attempt.max_cost_micros THEN
            RAISE EXCEPTION 'invalid actual provider cost' USING ERRCODE = '22023';
        END IF;
        UPDATE public.gabriel_provider_budget_periods
           SET uncertain_micros = uncertain_micros - v_attempt.max_cost_micros,
               settled_micros = settled_micros + p_actual_cost_micros,
               updated_at = pg_catalog.clock_timestamp()
         WHERE budget_id IN (v_global.budget_id, v_user.budget_id);
        v_actual := p_actual_cost_micros;
    ELSIF p_state = 'uncertain' THEN
        UPDATE public.gabriel_provider_budget_periods
           SET reserved_micros = reserved_micros - v_attempt.max_cost_micros,
               uncertain_micros = uncertain_micros + v_attempt.max_cost_micros,
               updated_at = pg_catalog.clock_timestamp()
         WHERE budget_id IN (v_global.budget_id, v_user.budget_id);
        v_actual := NULL;
    ELSE
        IF p_actual_cost_micros IS NULL OR p_actual_cost_micros < 0
           OR p_actual_cost_micros > v_attempt.max_cost_micros THEN
            RAISE EXCEPTION 'invalid actual provider cost' USING ERRCODE = '22023';
        END IF;
        UPDATE public.gabriel_provider_budget_periods
           SET reserved_micros = reserved_micros - v_attempt.max_cost_micros,
               settled_micros = settled_micros + p_actual_cost_micros,
               updated_at = pg_catalog.clock_timestamp()
         WHERE budget_id IN (v_global.budget_id, v_user.budget_id);
        v_actual := p_actual_cost_micros;
    END IF;
    GET DIAGNOSTICS v_updated = ROW_COUNT;
    IF v_updated <> 2 THEN
        RAISE EXCEPTION 'provider budget period update incomplete' USING ERRCODE = 'P0001';
    END IF;

    UPDATE public.gabriel_provider_budget_attempts
       SET state = p_state, actual_cost_micros = v_actual,
           updated_at = pg_catalog.clock_timestamp()
     WHERE budget_attempt_id = v_attempt.budget_attempt_id
     RETURNING * INTO v_attempt;
    RETURN pg_catalog.to_jsonb(v_attempt)
        || pg_catalog.jsonb_build_object('idempotent', false);
END;
$$;

REVOKE ALL ON FUNCTION public.gabriel_provider_budget_admin_set_policy(
    text, text, text, bigint, bigint, boolean, timestamptz, timestamptz
) FROM PUBLIC, anon, authenticated, service_role;
REVOKE ALL ON FUNCTION public.gabriel_provider_budget_lock_period(
    uuid, text, text, text, text, text, timestamptz, timestamptz, bigint
) FROM PUBLIC, anon, authenticated, service_role;
REVOKE ALL ON FUNCTION public.gabriel_provider_budget_reserve_attempt(
    text, text, uuid, integer, text, text, bigint, text
) FROM PUBLIC, anon, authenticated, service_role;
REVOKE ALL ON FUNCTION public.gabriel_provider_budget_settle_attempt(
    text, text, uuid, integer, text, bigint, bigint, bigint
) FROM PUBLIC, anon, authenticated, service_role;

GRANT EXECUTE ON FUNCTION public.gabriel_provider_budget_reserve_attempt(
    text, text, uuid, integer, text, text, bigint, text
) TO service_role;
GRANT EXECUTE ON FUNCTION public.gabriel_provider_budget_settle_attempt(
    text, text, uuid, integer, text, bigint, bigint, bigint
) TO service_role;

COMMIT;
