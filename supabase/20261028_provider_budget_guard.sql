-- Gabriel V3 - persistent provider budgets (inactive until application flags are enabled)
-- Additive migration.  Requires 20261024_credit_ledger_phase1.sql and
-- 20261026_credit_ledger_expiration_fix.sql.  Never runs automatically.

BEGIN;

CREATE TABLE public.gabriel_provider_budget_periods (
    budget_id uuid PRIMARY KEY DEFAULT pg_catalog.gen_random_uuid(),
    provider text NOT NULL,
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
    period_start timestamptz NOT NULL,
    period_end timestamptz NOT NULL,
    max_cost_micros bigint NOT NULL CHECK (max_cost_micros >= 0),
    actual_cost_micros bigint CHECK (
        actual_cost_micros IS NULL OR
        (actual_cost_micros >= 0 AND actual_cost_micros <= max_cost_micros)
    ),
    state text NOT NULL DEFAULT 'reserved'
        CHECK (state IN ('reserved', 'succeeded', 'failed', 'uncertain')),
    created_at timestamptz NOT NULL DEFAULT pg_catalog.clock_timestamp(),
    updated_at timestamptz NOT NULL DEFAULT pg_catalog.clock_timestamp(),
    UNIQUE (reservation_id, attempt_no)
);

CREATE INDEX gabriel_provider_budget_attempts_user_period_idx
    ON public.gabriel_provider_budget_attempts (user_id, provider, period_start);

ALTER TABLE public.gabriel_provider_budget_periods ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.gabriel_provider_budget_attempts ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON TABLE public.gabriel_provider_budget_periods FROM PUBLIC, anon, authenticated, service_role;
REVOKE ALL ON TABLE public.gabriel_provider_budget_attempts FROM PUBLIC, anon, authenticated, service_role;

CREATE OR REPLACE FUNCTION public.gabriel_provider_budget_lock_period(
    p_provider text,
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
    IF nullif(pg_catalog.btrim(p_provider), '') IS NULL
       OR p_scope_type NOT IN ('global', 'user')
       OR nullif(pg_catalog.btrim(p_scope_key), '') IS NULL
       OR p_period_start IS NULL OR p_period_end <= p_period_start
       OR p_limit_micros <= 0 THEN
        RAISE EXCEPTION 'invalid provider budget period';
    END IF;

    INSERT INTO public.gabriel_provider_budget_periods (
        provider, scope_type, scope_key, period_start, period_end, limit_micros
    ) VALUES (
        p_provider, p_scope_type, p_scope_key, p_period_start, p_period_end, p_limit_micros
    ) ON CONFLICT (provider, scope_type, scope_key, period_start) DO NOTHING;

    SELECT * INTO v_period
      FROM public.gabriel_provider_budget_periods
     WHERE provider = p_provider
       AND scope_type = p_scope_type
       AND scope_key = p_scope_key
       AND period_start = p_period_start
     FOR UPDATE;

    IF v_period.period_end IS DISTINCT FROM p_period_end
       OR v_period.limit_micros <> p_limit_micros THEN
        RAISE EXCEPTION 'provider budget policy changed inside an active period';
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
    p_provider_request_id text,
    p_period_start timestamptz,
    p_period_end timestamptz,
    p_user_limit_micros bigint,
    p_global_limit_micros bigint
) RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
    v_existing public.gabriel_provider_budget_attempts%ROWTYPE;
    v_global public.gabriel_provider_budget_periods%ROWTYPE;
    v_user public.gabriel_provider_budget_periods%ROWTYPE;
    v_attempt public.gabriel_provider_budget_attempts%ROWTYPE;
BEGIN
    PERFORM public.gabriel_credit_assert_actor(p_authenticated_user_id, p_user_id);
    IF p_max_cost_micros < 0 OR p_attempt_no <= 0
       OR p_user_limit_micros <= 0 OR p_global_limit_micros <= 0
       OR p_user_limit_micros > p_global_limit_micros THEN
        RAISE EXCEPTION 'invalid provider attempt budget';
    END IF;

    -- Lock order is reservation -> global period -> user period everywhere.
    -- If a later budget check fails, the nested ledger attempt is rolled back
    -- by this same transaction: no orphan provider usage can be created.
    PERFORM public.gabriel_credit_record_provider_attempt(
        p_authenticated_user_id, p_user_id, p_reservation_id, p_attempt_no,
        p_provider, p_model, p_max_cost_micros, p_provider_request_id
    );

    SELECT * INTO v_existing
      FROM public.gabriel_provider_budget_attempts
     WHERE reservation_id = p_reservation_id AND attempt_no = p_attempt_no;
    IF FOUND THEN
        IF v_existing.user_id <> p_user_id
           OR v_existing.provider <> p_provider
           OR v_existing.model <> p_model
           OR v_existing.max_cost_micros <> p_max_cost_micros
           OR v_existing.period_start IS DISTINCT FROM p_period_start
           OR v_existing.period_end IS DISTINCT FROM p_period_end THEN
            RAISE EXCEPTION 'provider budget attempt idempotency conflict';
        END IF;
        RETURN pg_catalog.to_jsonb(v_existing) || pg_catalog.jsonb_build_object('idempotent', true);
    END IF;

    v_global := public.gabriel_provider_budget_lock_period(
        p_provider, 'global', 'global', p_period_start, p_period_end, p_global_limit_micros
    );
    v_user := public.gabriel_provider_budget_lock_period(
        p_provider, 'user', p_user_id, p_period_start, p_period_end, p_user_limit_micros
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
        period_start, period_end, max_cost_micros
    ) VALUES (
        p_reservation_id, p_attempt_no, p_user_id, p_provider, p_model,
        p_period_start, p_period_end, p_max_cost_micros
    ) RETURNING * INTO v_attempt;
    UPDATE public.gabriel_provider_budget_periods
       SET reserved_micros = reserved_micros + p_max_cost_micros,
           updated_at = pg_catalog.clock_timestamp()
     WHERE budget_id IN (v_global.budget_id, v_user.budget_id);
    RETURN pg_catalog.to_jsonb(v_attempt) || pg_catalog.jsonb_build_object('idempotent', false);
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
BEGIN
    PERFORM public.gabriel_credit_assert_actor(p_authenticated_user_id, p_user_id);
    IF p_state NOT IN ('succeeded', 'failed', 'uncertain') THEN
        RAISE EXCEPTION 'invalid provider budget settlement state';
    END IF;

    -- The certified ledger RPC locks the reservation and usage first.  Every
    -- budget writer follows that same order, preventing lock inversion.
    PERFORM public.gabriel_credit_settle_provider_attempt(
        p_authenticated_user_id, p_user_id, p_reservation_id, p_attempt_no,
        p_state, p_actual_cost_micros, p_input_tokens, p_output_tokens
    );
    SELECT * INTO v_attempt
      FROM public.gabriel_provider_budget_attempts
     WHERE reservation_id = p_reservation_id AND attempt_no = p_attempt_no
     FOR UPDATE;
    IF NOT FOUND OR v_attempt.user_id <> p_user_id THEN
        RAISE EXCEPTION 'provider budget attempt not found';
    END IF;
    IF v_attempt.state <> 'reserved' THEN
        IF v_attempt.state = 'uncertain'
           AND p_state IN ('succeeded', 'failed')
           AND p_actual_cost_micros IS NOT NULL THEN
            v_reconcile_uncertain := true;
        ELSIF v_attempt.state <> p_state
           OR v_attempt.actual_cost_micros IS DISTINCT FROM p_actual_cost_micros THEN
            RAISE EXCEPTION 'provider budget settlement idempotency conflict';
        ELSE
            RETURN pg_catalog.to_jsonb(v_attempt) || pg_catalog.jsonb_build_object('idempotent', true);
        END IF;
    END IF;

    v_global := public.gabriel_provider_budget_lock_period(
        v_attempt.provider, 'global', 'global', v_attempt.period_start,
        v_attempt.period_end,
        (SELECT limit_micros FROM public.gabriel_provider_budget_periods
          WHERE provider = v_attempt.provider AND scope_type = 'global'
            AND scope_key = 'global' AND period_start = v_attempt.period_start)
    );
    v_user := public.gabriel_provider_budget_lock_period(
        v_attempt.provider, 'user', p_user_id, v_attempt.period_start,
        v_attempt.period_end,
        (SELECT limit_micros FROM public.gabriel_provider_budget_periods
          WHERE provider = v_attempt.provider AND scope_type = 'user'
            AND scope_key = p_user_id AND period_start = v_attempt.period_start)
    );

    IF v_reconcile_uncertain THEN
        IF p_actual_cost_micros < 0 OR p_actual_cost_micros > v_attempt.max_cost_micros THEN
            RAISE EXCEPTION 'invalid actual provider cost';
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
            RAISE EXCEPTION 'invalid actual provider cost';
        END IF;
        UPDATE public.gabriel_provider_budget_periods
           SET reserved_micros = reserved_micros - v_attempt.max_cost_micros,
               settled_micros = settled_micros + p_actual_cost_micros,
               updated_at = pg_catalog.clock_timestamp()
         WHERE budget_id IN (v_global.budget_id, v_user.budget_id);
        v_actual := p_actual_cost_micros;
    END IF;
    UPDATE public.gabriel_provider_budget_attempts
       SET state = p_state, actual_cost_micros = v_actual,
           updated_at = pg_catalog.clock_timestamp()
     WHERE budget_attempt_id = v_attempt.budget_attempt_id
     RETURNING * INTO v_attempt;
    RETURN pg_catalog.to_jsonb(v_attempt) || pg_catalog.jsonb_build_object('idempotent', false);
END;
$$;

REVOKE ALL ON FUNCTION public.gabriel_provider_budget_lock_period(
    text, text, text, timestamptz, timestamptz, bigint
) FROM PUBLIC, anon, authenticated, service_role;
REVOKE ALL ON FUNCTION public.gabriel_provider_budget_reserve_attempt(
    text, text, uuid, integer, text, text, bigint, text,
    timestamptz, timestamptz, bigint, bigint
) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.gabriel_provider_budget_settle_attempt(
    text, text, uuid, integer, text, bigint, bigint, bigint
) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.gabriel_provider_budget_reserve_attempt(
    text, text, uuid, integer, text, text, bigint, text,
    timestamptz, timestamptz, bigint, bigint
) TO service_role;
GRANT EXECUTE ON FUNCTION public.gabriel_provider_budget_settle_attempt(
    text, text, uuid, integer, text, bigint, bigint, bigint
) TO service_role;

COMMIT;
