-- Gabriel V3 - Credit ledger, phase 1
-- Local/versioned migration. DO NOT APPLY TO A REMOTE PROJECT before review.
--
-- Non-destructive guarantees:
--   * creates new gabriel_credit_* objects only;
--   * never updates or deletes gabriel_users.credits;
--   * legacy balances are imported only by an explicit, idempotent RPC;
--   * the financial event ledger is append-only.

BEGIN;

CREATE TABLE IF NOT EXISTS public.gabriel_credit_accounts (
    user_id                 text PRIMARY KEY,
    available_credits       bigint NOT NULL DEFAULT 0 CHECK (available_credits >= 0),
    reserved_credits        bigint NOT NULL DEFAULT 0 CHECK (reserved_credits >= 0),
    lifetime_granted        bigint NOT NULL DEFAULT 0 CHECK (lifetime_granted >= 0),
    lifetime_captured       bigint NOT NULL DEFAULT 0 CHECK (lifetime_captured >= 0),
    created_at              timestamptz NOT NULL DEFAULT now(),
    updated_at              timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.gabriel_credit_grants (
    grant_id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id                 text NOT NULL REFERENCES public.gabriel_credit_accounts(user_id),
    source_type             text NOT NULL CHECK (source_type IN (
                                'legacy_migration', 'signup', 'subscription',
                                'topup', 'refund', 'adjustment'
                            )),
    source_key              text NOT NULL,
    granted_credits         bigint NOT NULL CHECK (granted_credits > 0),
    remaining_credits       bigint NOT NULL CHECK (remaining_credits >= 0),
    reserved_credits        bigint NOT NULL DEFAULT 0 CHECK (reserved_credits >= 0),
    starts_at               timestamptz NOT NULL DEFAULT now(),
    expires_at              timestamptz,
    metadata                jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at              timestamptz NOT NULL DEFAULT now(),
    UNIQUE (user_id, source_key),
    CHECK (remaining_credits + reserved_credits <= granted_credits),
    CHECK (expires_at IS NULL OR expires_at > starts_at)
);

CREATE INDEX IF NOT EXISTS idx_gabriel_credit_grants_spend_order
    ON public.gabriel_credit_grants (user_id, expires_at, created_at)
    WHERE remaining_credits > 0;

CREATE TABLE IF NOT EXISTS public.gabriel_credit_legacy_snapshots (
    user_id                 text PRIMARY KEY REFERENCES public.gabriel_credit_accounts(user_id),
    legacy_credits          bigint NOT NULL CHECK (legacy_credits >= 0),
    snapshot_key            text NOT NULL UNIQUE,
    imported_at             timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS public.gabriel_credit_reservations (
    reservation_id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id                 text NOT NULL REFERENCES public.gabriel_credit_accounts(user_id),
    operation_type          text NOT NULL,
    idempotency_key         text NOT NULL,
    request_hash            text NOT NULL,
    pricing_version         text NOT NULL DEFAULT 'phase1-provisional',
    quoted_credits          bigint NOT NULL CHECK (quoted_credits > 0),
    provider_budget_micros  bigint NOT NULL CHECK (provider_budget_micros >= 0),
    provider_spent_micros   bigint NOT NULL DEFAULT 0 CHECK (provider_spent_micros >= 0),
    uncertain_provider_micros bigint NOT NULL DEFAULT 0 CHECK (uncertain_provider_micros >= 0),
    captured_credits        bigint NOT NULL DEFAULT 0 CHECK (captured_credits >= 0),
    status                  text NOT NULL DEFAULT 'reserved' CHECK (status IN (
                                'reserved', 'running', 'uncertain',
                                'captured', 'released'
                            )),
    created_at              timestamptz NOT NULL DEFAULT now(),
    updated_at              timestamptz NOT NULL DEFAULT now(),
    finalised_at            timestamptz,
    UNIQUE (user_id, idempotency_key),
    CHECK (captured_credits <= quoted_credits),
    CHECK (provider_spent_micros <= provider_budget_micros),
    CHECK (uncertain_provider_micros <= provider_budget_micros)
);

CREATE INDEX IF NOT EXISTS idx_gabriel_credit_reservations_open
    ON public.gabriel_credit_reservations (user_id, created_at)
    WHERE status IN ('reserved', 'running', 'uncertain');

CREATE TABLE IF NOT EXISTS public.gabriel_credit_allocations (
    reservation_id          uuid NOT NULL REFERENCES public.gabriel_credit_reservations(reservation_id),
    grant_id                uuid NOT NULL REFERENCES public.gabriel_credit_grants(grant_id),
    reserved_credits        bigint NOT NULL CHECK (reserved_credits > 0),
    captured_credits        bigint NOT NULL DEFAULT 0 CHECK (captured_credits >= 0),
    released_credits        bigint NOT NULL DEFAULT 0 CHECK (released_credits >= 0),
    PRIMARY KEY (reservation_id, grant_id),
    CHECK (captured_credits + released_credits <= reserved_credits)
);

CREATE TABLE IF NOT EXISTS public.gabriel_credit_provider_usage (
    usage_id                uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    reservation_id          uuid NOT NULL REFERENCES public.gabriel_credit_reservations(reservation_id),
    attempt_no              integer NOT NULL CHECK (attempt_no > 0),
    provider                text NOT NULL,
    model                   text NOT NULL,
    state                   text NOT NULL DEFAULT 'started' CHECK (state IN (
                                'started', 'succeeded', 'failed', 'uncertain'
                            )),
    max_cost_micros         bigint NOT NULL CHECK (max_cost_micros >= 0),
    actual_cost_micros      bigint CHECK (actual_cost_micros >= 0),
    input_tokens            bigint CHECK (input_tokens >= 0),
    output_tokens           bigint CHECK (output_tokens >= 0),
    provider_request_id     text,
    created_at              timestamptz NOT NULL DEFAULT now(),
    updated_at              timestamptz NOT NULL DEFAULT now(),
    UNIQUE (reservation_id, attempt_no),
    CHECK (actual_cost_micros IS NULL OR actual_cost_micros <= max_cost_micros)
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_gabriel_credit_provider_request
    ON public.gabriel_credit_provider_usage (provider, provider_request_id)
    WHERE provider_request_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS public.gabriel_credit_ledger (
    sequence_no             bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    event_id                uuid NOT NULL UNIQUE DEFAULT gen_random_uuid(),
    user_id                 text NOT NULL,
    event_type              text NOT NULL CHECK (event_type IN (
                                'grant', 'legacy_import', 'reserve', 'capture',
                                'release', 'uncertain', 'expire', 'adjustment'
                            )),
    grant_id                uuid REFERENCES public.gabriel_credit_grants(grant_id),
    reservation_id          uuid REFERENCES public.gabriel_credit_reservations(reservation_id),
    delta_available         bigint NOT NULL DEFAULT 0,
    delta_reserved          bigint NOT NULL DEFAULT 0,
    delta_consumed          bigint NOT NULL DEFAULT 0,
    provider_micros         bigint NOT NULL DEFAULT 0 CHECK (provider_micros >= 0),
    metadata                jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at              timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_gabriel_credit_ledger_user_sequence
    ON public.gabriel_credit_ledger (user_id, sequence_no);

CREATE OR REPLACE FUNCTION public.gabriel_credit_ledger_immutable()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = pg_catalog, pg_temp
AS $$
BEGIN
    RAISE EXCEPTION 'gabriel_credit_ledger is append-only';
END;
$$;

DROP TRIGGER IF EXISTS trg_gabriel_credit_ledger_immutable
    ON public.gabriel_credit_ledger;
CREATE TRIGGER trg_gabriel_credit_ledger_immutable
BEFORE UPDATE OR DELETE ON public.gabriel_credit_ledger
FOR EACH ROW EXECUTE FUNCTION public.gabriel_credit_ledger_immutable();

CREATE OR REPLACE FUNCTION public.gabriel_credit_assert_actor(
    p_authenticated_user_id text,
    p_user_id text
) RETURNS void
LANGUAGE plpgsql
IMMUTABLE
SET search_path = pg_catalog, pg_temp
AS $$
BEGIN
    IF nullif(btrim(p_authenticated_user_id), '') IS NULL
       OR p_authenticated_user_id IS DISTINCT FROM p_user_id THEN
        RAISE EXCEPTION 'credit ledger identity mismatch' USING ERRCODE = '42501';
    END IF;
END;
$$;

CREATE OR REPLACE FUNCTION public.gabriel_credit_grant(
    p_authenticated_user_id text,
    p_user_id text,
    p_credits bigint,
    p_source_type text,
    p_source_key text,
    p_expires_at timestamptz DEFAULT NULL,
    p_metadata jsonb DEFAULT '{}'::jsonb
) RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
    v_existing public.gabriel_credit_grants%ROWTYPE;
    v_grant public.gabriel_credit_grants%ROWTYPE;
BEGIN
    PERFORM public.gabriel_credit_assert_actor(p_authenticated_user_id, p_user_id);
    IF p_credits <= 0 OR nullif(btrim(p_source_key), '') IS NULL THEN
        RAISE EXCEPTION 'invalid credit grant';
    END IF;

    INSERT INTO public.gabriel_credit_accounts (user_id)
    VALUES (p_user_id) ON CONFLICT (user_id) DO NOTHING;
    PERFORM 1 FROM public.gabriel_credit_accounts
      WHERE user_id = p_user_id FOR UPDATE;

    SELECT * INTO v_existing
      FROM public.gabriel_credit_grants
     WHERE user_id = p_user_id AND source_key = p_source_key;
    IF FOUND THEN
        IF v_existing.granted_credits <> p_credits
           OR v_existing.source_type <> p_source_type
           OR v_existing.expires_at IS DISTINCT FROM p_expires_at THEN
            RAISE EXCEPTION 'grant idempotency conflict';
        END IF;
        RETURN to_jsonb(v_existing) || jsonb_build_object('idempotent', true);
    END IF;

    INSERT INTO public.gabriel_credit_grants (
        user_id, source_type, source_key, granted_credits,
        remaining_credits, expires_at, metadata
    ) VALUES (
        p_user_id, p_source_type, p_source_key, p_credits,
        p_credits, p_expires_at, coalesce(p_metadata, '{}'::jsonb)
    ) RETURNING * INTO v_grant;

    UPDATE public.gabriel_credit_accounts
       SET available_credits = available_credits + p_credits,
           lifetime_granted = lifetime_granted + p_credits,
           updated_at = now()
     WHERE user_id = p_user_id;

    INSERT INTO public.gabriel_credit_ledger (
        user_id, event_type, grant_id, delta_available, metadata
    ) VALUES (
        p_user_id, 'grant', v_grant.grant_id, p_credits,
        jsonb_build_object('source_type', p_source_type, 'source_key', p_source_key)
    );
    RETURN to_jsonb(v_grant) || jsonb_build_object('idempotent', false);
END;
$$;

CREATE OR REPLACE FUNCTION public.gabriel_credit_import_legacy_balance(
    p_authenticated_user_id text,
    p_user_id text,
    p_legacy_credits bigint,
    p_snapshot_key text
) RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
    v_snapshot public.gabriel_credit_legacy_snapshots%ROWTYPE;
    v_grant_id uuid;
BEGIN
    PERFORM public.gabriel_credit_assert_actor(p_authenticated_user_id, p_user_id);
    IF p_legacy_credits < 0 OR nullif(btrim(p_snapshot_key), '') IS NULL THEN
        RAISE EXCEPTION 'invalid legacy snapshot';
    END IF;

    INSERT INTO public.gabriel_credit_accounts (user_id)
    VALUES (p_user_id) ON CONFLICT (user_id) DO NOTHING;
    PERFORM 1 FROM public.gabriel_credit_accounts
      WHERE user_id = p_user_id FOR UPDATE;

    SELECT * INTO v_snapshot FROM public.gabriel_credit_legacy_snapshots
     WHERE user_id = p_user_id;
    IF FOUND THEN
        IF v_snapshot.legacy_credits <> p_legacy_credits
           OR v_snapshot.snapshot_key <> p_snapshot_key THEN
            RAISE EXCEPTION 'legacy balance already snapshotted with different data';
        END IF;
        RETURN jsonb_build_object(
            'user_id', p_user_id, 'legacy_credits', p_legacy_credits,
            'snapshot_key', p_snapshot_key, 'idempotent', true
        );
    END IF;

    INSERT INTO public.gabriel_credit_legacy_snapshots
        (user_id, legacy_credits, snapshot_key)
    VALUES (p_user_id, p_legacy_credits, p_snapshot_key);

    IF p_legacy_credits > 0 THEN
        INSERT INTO public.gabriel_credit_grants (
            user_id, source_type, source_key, granted_credits,
            remaining_credits, metadata
        ) VALUES (
            p_user_id, 'legacy_migration', 'legacy:' || p_snapshot_key,
            p_legacy_credits, p_legacy_credits,
            jsonb_build_object('snapshot_key', p_snapshot_key)
        ) RETURNING grant_id INTO v_grant_id;

        UPDATE public.gabriel_credit_accounts
           SET available_credits = available_credits + p_legacy_credits,
               lifetime_granted = lifetime_granted + p_legacy_credits,
               updated_at = now()
         WHERE user_id = p_user_id;
        INSERT INTO public.gabriel_credit_ledger (
            user_id, event_type, grant_id, delta_available, metadata
        ) VALUES (
            p_user_id, 'legacy_import', v_grant_id, p_legacy_credits,
            jsonb_build_object('snapshot_key', p_snapshot_key)
        );
    END IF;

    RETURN jsonb_build_object(
        'user_id', p_user_id, 'legacy_credits', p_legacy_credits,
        'snapshot_key', p_snapshot_key, 'idempotent', false
    );
END;
$$;

CREATE OR REPLACE FUNCTION public.gabriel_credit_reserve(
    p_authenticated_user_id text,
    p_user_id text,
    p_operation_type text,
    p_idempotency_key text,
    p_request_hash text,
    p_credits bigint,
    p_provider_budget_micros bigint,
    p_pricing_version text DEFAULT 'phase1-provisional'
) RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
    v_account public.gabriel_credit_accounts%ROWTYPE;
    v_existing public.gabriel_credit_reservations%ROWTYPE;
    v_reservation public.gabriel_credit_reservations%ROWTYPE;
    v_grant public.gabriel_credit_grants%ROWTYPE;
    v_remaining bigint;
    v_allocated bigint;
BEGIN
    PERFORM public.gabriel_credit_assert_actor(p_authenticated_user_id, p_user_id);
    IF p_credits <= 0 OR p_provider_budget_micros < 0
       OR nullif(btrim(p_operation_type), '') IS NULL
       OR nullif(btrim(p_idempotency_key), '') IS NULL
       OR nullif(btrim(p_request_hash), '') IS NULL THEN
        RAISE EXCEPTION 'invalid reservation';
    END IF;

    SELECT * INTO v_account FROM public.gabriel_credit_accounts
     WHERE user_id = p_user_id FOR UPDATE;
    IF NOT FOUND THEN
        RAISE EXCEPTION 'insufficient credits' USING ERRCODE = 'P0001';
    END IF;

    SELECT * INTO v_existing FROM public.gabriel_credit_reservations
     WHERE user_id = p_user_id AND idempotency_key = p_idempotency_key;
    IF FOUND THEN
        IF v_existing.operation_type <> p_operation_type
           OR v_existing.request_hash <> p_request_hash
           OR v_existing.quoted_credits <> p_credits
           OR v_existing.provider_budget_micros <> p_provider_budget_micros
           OR v_existing.pricing_version <> p_pricing_version THEN
            RAISE EXCEPTION 'reservation idempotency conflict';
        END IF;
        RETURN to_jsonb(v_existing) || jsonb_build_object('idempotent', true);
    END IF;
    IF v_account.available_credits < p_credits THEN
        RAISE EXCEPTION 'insufficient credits' USING ERRCODE = 'P0001';
    END IF;

    INSERT INTO public.gabriel_credit_reservations (
        user_id, operation_type, idempotency_key, request_hash,
        pricing_version, quoted_credits, provider_budget_micros
    ) VALUES (
        p_user_id, p_operation_type, p_idempotency_key, p_request_hash,
        p_pricing_version, p_credits, p_provider_budget_micros
    ) RETURNING * INTO v_reservation;

    v_remaining := p_credits;
    FOR v_grant IN
        SELECT * FROM public.gabriel_credit_grants
         WHERE user_id = p_user_id AND remaining_credits > 0
           AND starts_at <= now()
           AND (expires_at IS NULL OR expires_at > now())
         ORDER BY expires_at ASC NULLS LAST, created_at, grant_id
         FOR UPDATE
    LOOP
        EXIT WHEN v_remaining = 0;
        v_allocated := least(v_remaining, v_grant.remaining_credits);
        UPDATE public.gabriel_credit_grants
           SET remaining_credits = remaining_credits - v_allocated,
               reserved_credits = reserved_credits + v_allocated
         WHERE grant_id = v_grant.grant_id;
        INSERT INTO public.gabriel_credit_allocations
            (reservation_id, grant_id, reserved_credits)
        VALUES (v_reservation.reservation_id, v_grant.grant_id, v_allocated);
        v_remaining := v_remaining - v_allocated;
    END LOOP;
    IF v_remaining <> 0 THEN
        RAISE EXCEPTION 'account and grant balances diverged';
    END IF;

    UPDATE public.gabriel_credit_accounts
       SET available_credits = available_credits - p_credits,
           reserved_credits = reserved_credits + p_credits,
           updated_at = now()
     WHERE user_id = p_user_id;
    INSERT INTO public.gabriel_credit_ledger (
        user_id, event_type, reservation_id, delta_available,
        delta_reserved, provider_micros, metadata
    ) VALUES (
        p_user_id, 'reserve', v_reservation.reservation_id,
        -p_credits, p_credits, p_provider_budget_micros,
        jsonb_build_object('operation_type', p_operation_type,
                           'pricing_version', p_pricing_version)
    );
    RETURN to_jsonb(v_reservation) || jsonb_build_object('idempotent', false);
END;
$$;

CREATE OR REPLACE FUNCTION public.gabriel_credit_record_provider_attempt(
    p_authenticated_user_id text,
    p_user_id text,
    p_reservation_id uuid,
    p_attempt_no integer,
    p_provider text,
    p_model text,
    p_max_cost_micros bigint,
    p_provider_request_id text DEFAULT NULL
) RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
    v_reservation public.gabriel_credit_reservations%ROWTYPE;
    v_existing public.gabriel_credit_provider_usage%ROWTYPE;
    v_usage public.gabriel_credit_provider_usage%ROWTYPE;
    v_reserved bigint;
BEGIN
    PERFORM public.gabriel_credit_assert_actor(p_authenticated_user_id, p_user_id);
    SELECT * INTO v_reservation FROM public.gabriel_credit_reservations
     WHERE reservation_id = p_reservation_id AND user_id = p_user_id FOR UPDATE;
    IF NOT FOUND THEN RAISE EXCEPTION 'reservation not found'; END IF;

    SELECT * INTO v_existing FROM public.gabriel_credit_provider_usage
     WHERE reservation_id = p_reservation_id AND attempt_no = p_attempt_no;
    IF FOUND THEN
        IF v_existing.provider <> p_provider OR v_existing.model <> p_model
           OR v_existing.max_cost_micros <> p_max_cost_micros
           OR v_existing.provider_request_id IS DISTINCT FROM p_provider_request_id THEN
            RAISE EXCEPTION 'provider attempt idempotency conflict';
        END IF;
        RETURN to_jsonb(v_existing) || jsonb_build_object('idempotent', true);
    END IF;
    IF v_reservation.status NOT IN ('reserved', 'running') THEN
        RAISE EXCEPTION 'provider attempt not allowed from state %', v_reservation.status;
    END IF;
    SELECT coalesce(sum(max_cost_micros), 0) INTO v_reserved
      FROM public.gabriel_credit_provider_usage
     WHERE reservation_id = p_reservation_id;
    IF p_attempt_no <= 0 OR p_max_cost_micros < 0
       OR v_reserved + p_max_cost_micros > v_reservation.provider_budget_micros THEN
        RAISE EXCEPTION 'provider attempt exceeds reservation budget';
    END IF;

    INSERT INTO public.gabriel_credit_provider_usage (
        reservation_id, attempt_no, provider, model, max_cost_micros,
        provider_request_id
    ) VALUES (
        p_reservation_id, p_attempt_no, p_provider, p_model,
        p_max_cost_micros, p_provider_request_id
    ) RETURNING * INTO v_usage;
    UPDATE public.gabriel_credit_reservations
       SET status = 'running', updated_at = now()
     WHERE reservation_id = p_reservation_id;
    RETURN to_jsonb(v_usage) || jsonb_build_object('idempotent', false);
END;
$$;

CREATE OR REPLACE FUNCTION public.gabriel_credit_settle_provider_attempt(
    p_authenticated_user_id text,
    p_user_id text,
    p_reservation_id uuid,
    p_attempt_no integer,
    p_state text,
    p_actual_cost_micros bigint DEFAULT NULL,
    p_input_tokens bigint DEFAULT NULL,
    p_output_tokens bigint DEFAULT NULL
) RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
    v_usage public.gabriel_credit_provider_usage%ROWTYPE;
BEGIN
    PERFORM public.gabriel_credit_assert_actor(p_authenticated_user_id, p_user_id);
    PERFORM 1 FROM public.gabriel_credit_reservations
     WHERE reservation_id = p_reservation_id AND user_id = p_user_id FOR UPDATE;
    IF NOT FOUND THEN RAISE EXCEPTION 'reservation not found'; END IF;
    SELECT * INTO v_usage FROM public.gabriel_credit_provider_usage
     WHERE reservation_id = p_reservation_id AND attempt_no = p_attempt_no FOR UPDATE;
    IF NOT FOUND THEN RAISE EXCEPTION 'provider attempt not found'; END IF;
    IF p_state NOT IN ('succeeded', 'failed', 'uncertain')
       OR (p_state IN ('succeeded', 'failed') AND p_actual_cost_micros IS NULL)
       OR p_actual_cost_micros < 0
       OR p_actual_cost_micros > v_usage.max_cost_micros THEN
        RAISE EXCEPTION 'invalid provider settlement';
    END IF;
    IF v_usage.state <> 'started'
       AND NOT (v_usage.state = 'uncertain'
                AND p_state IN ('succeeded', 'failed')
                AND p_actual_cost_micros IS NOT NULL) THEN
        IF v_usage.state <> p_state
           OR v_usage.actual_cost_micros IS DISTINCT FROM p_actual_cost_micros
           OR v_usage.input_tokens IS DISTINCT FROM p_input_tokens
           OR v_usage.output_tokens IS DISTINCT FROM p_output_tokens THEN
            RAISE EXCEPTION 'provider settlement idempotency conflict';
        END IF;
        RETURN to_jsonb(v_usage) || jsonb_build_object('idempotent', true);
    END IF;
    UPDATE public.gabriel_credit_provider_usage
       SET state = p_state, actual_cost_micros = p_actual_cost_micros,
           input_tokens = p_input_tokens, output_tokens = p_output_tokens,
           updated_at = now()
     WHERE usage_id = v_usage.usage_id RETURNING * INTO v_usage;
    RETURN to_jsonb(v_usage) || jsonb_build_object('idempotent', false);
END;
$$;

CREATE OR REPLACE FUNCTION public.gabriel_credit_release(
    p_authenticated_user_id text,
    p_user_id text,
    p_reservation_id uuid
) RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
    v_reservation public.gabriel_credit_reservations%ROWTYPE;
    v_allocation public.gabriel_credit_allocations%ROWTYPE;
BEGIN
    PERFORM public.gabriel_credit_assert_actor(p_authenticated_user_id, p_user_id);
    SELECT * INTO v_reservation FROM public.gabriel_credit_reservations
     WHERE reservation_id = p_reservation_id AND user_id = p_user_id FOR UPDATE;
    IF NOT FOUND THEN RAISE EXCEPTION 'reservation not found'; END IF;
    IF v_reservation.status = 'released' THEN
        RETURN to_jsonb(v_reservation) || jsonb_build_object('idempotent', true);
    END IF;
    IF v_reservation.status <> 'reserved'
       OR EXISTS (SELECT 1 FROM public.gabriel_credit_provider_usage
                   WHERE reservation_id = p_reservation_id) THEN
        RAISE EXCEPTION 'only a never-started reservation can be released';
    END IF;

    FOR v_allocation IN SELECT * FROM public.gabriel_credit_allocations
                         WHERE reservation_id = p_reservation_id FOR UPDATE
    LOOP
        UPDATE public.gabriel_credit_grants
           SET reserved_credits = reserved_credits - v_allocation.reserved_credits,
               remaining_credits = remaining_credits + v_allocation.reserved_credits
         WHERE grant_id = v_allocation.grant_id;
        UPDATE public.gabriel_credit_allocations
           SET released_credits = reserved_credits
         WHERE reservation_id = p_reservation_id
           AND grant_id = v_allocation.grant_id;
    END LOOP;
    UPDATE public.gabriel_credit_accounts
       SET available_credits = available_credits + v_reservation.quoted_credits,
           reserved_credits = reserved_credits - v_reservation.quoted_credits,
           updated_at = now() WHERE user_id = p_user_id;
    UPDATE public.gabriel_credit_reservations
       SET status = 'released', finalised_at = now(), updated_at = now()
     WHERE reservation_id = p_reservation_id RETURNING * INTO v_reservation;
    INSERT INTO public.gabriel_credit_ledger (
        user_id, event_type, reservation_id, delta_available, delta_reserved
    ) VALUES (
        p_user_id, 'release', p_reservation_id,
        v_reservation.quoted_credits, -v_reservation.quoted_credits
    );
    RETURN to_jsonb(v_reservation) || jsonb_build_object('idempotent', false);
END;
$$;

CREATE OR REPLACE FUNCTION public.gabriel_credit_capture(
    p_authenticated_user_id text,
    p_user_id text,
    p_reservation_id uuid,
    p_captured_credits bigint DEFAULT NULL,
    p_provider_spent_micros bigint DEFAULT 0
) RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
    v_reservation public.gabriel_credit_reservations%ROWTYPE;
    v_allocation public.gabriel_credit_allocations%ROWTYPE;
    v_capture bigint;
    v_alloc_capture bigint;
    v_alloc_release bigint;
    v_remaining_capture bigint;
    v_released bigint := 0;
    v_attempts bigint;
    v_billable_ceiling bigint;
    v_pending_attempts bigint;
BEGIN
    PERFORM public.gabriel_credit_assert_actor(p_authenticated_user_id, p_user_id);
    SELECT * INTO v_reservation FROM public.gabriel_credit_reservations
     WHERE reservation_id = p_reservation_id AND user_id = p_user_id FOR UPDATE;
    IF NOT FOUND THEN RAISE EXCEPTION 'reservation not found'; END IF;
    v_capture := coalesce(p_captured_credits, v_reservation.quoted_credits);
    IF v_capture < 0 OR v_capture > v_reservation.quoted_credits
       OR p_provider_spent_micros < 0
       OR p_provider_spent_micros > v_reservation.provider_budget_micros THEN
        RAISE EXCEPTION 'capture exceeds reservation';
    END IF;
    IF v_reservation.status = 'captured' THEN
        IF v_reservation.captured_credits <> v_capture
           OR v_reservation.provider_spent_micros <> p_provider_spent_micros THEN
            RAISE EXCEPTION 'capture idempotency conflict';
        END IF;
        RETURN to_jsonb(v_reservation) || jsonb_build_object('idempotent', true);
    END IF;
    IF v_reservation.status NOT IN ('reserved', 'running', 'uncertain') THEN
        RAISE EXCEPTION 'reservation cannot be captured from state %', v_reservation.status;
    END IF;
    SELECT count(*),
           count(*) FILTER (WHERE state IN ('started', 'uncertain')),
           coalesce(sum(actual_cost_micros), 0)
      INTO v_attempts, v_pending_attempts, v_billable_ceiling
      FROM public.gabriel_credit_provider_usage
     WHERE reservation_id = p_reservation_id;
    IF v_capture > 0 AND v_attempts = 0 THEN
        RAISE EXCEPTION 'credits cannot be captured before a provider attempt';
    END IF;
    IF v_pending_attempts > 0 THEN
        RAISE EXCEPTION 'provider usage must be reconciled before capture';
    END IF;
    IF p_provider_spent_micros > v_billable_ceiling THEN
        RAISE EXCEPTION 'provider spend exceeds settled usage';
    END IF;

    v_remaining_capture := v_capture;
    FOR v_allocation IN SELECT * FROM public.gabriel_credit_allocations
                         WHERE reservation_id = p_reservation_id
                         ORDER BY grant_id FOR UPDATE
    LOOP
        v_alloc_capture := least(v_remaining_capture, v_allocation.reserved_credits);
        v_alloc_release := v_allocation.reserved_credits - v_alloc_capture;
        v_remaining_capture := v_remaining_capture - v_alloc_capture;
        v_released := v_released + v_alloc_release;
        UPDATE public.gabriel_credit_allocations
           SET captured_credits = v_alloc_capture,
               released_credits = v_alloc_release
         WHERE reservation_id = p_reservation_id
           AND grant_id = v_allocation.grant_id;
        UPDATE public.gabriel_credit_grants
           SET reserved_credits = reserved_credits - v_allocation.reserved_credits,
               remaining_credits = remaining_credits + v_alloc_release
         WHERE grant_id = v_allocation.grant_id;
    END LOOP;
    IF v_remaining_capture <> 0 THEN
        RAISE EXCEPTION 'allocation total lower than capture';
    END IF;

    UPDATE public.gabriel_credit_accounts
       SET available_credits = available_credits + v_released,
           reserved_credits = reserved_credits - v_reservation.quoted_credits,
           lifetime_captured = lifetime_captured + v_capture,
           updated_at = now() WHERE user_id = p_user_id;
    UPDATE public.gabriel_credit_reservations
       SET status = 'captured', captured_credits = v_capture,
           provider_spent_micros = p_provider_spent_micros,
           uncertain_provider_micros = 0,
           finalised_at = now(), updated_at = now()
     WHERE reservation_id = p_reservation_id RETURNING * INTO v_reservation;
    IF v_capture > 0 THEN
        INSERT INTO public.gabriel_credit_ledger (
            user_id, event_type, reservation_id, delta_reserved,
            delta_consumed, provider_micros
        ) VALUES (
            p_user_id, 'capture', p_reservation_id, -v_capture,
            v_capture, p_provider_spent_micros
        );
    END IF;
    IF v_released > 0 THEN
        INSERT INTO public.gabriel_credit_ledger (
            user_id, event_type, reservation_id, delta_available, delta_reserved
        ) VALUES (p_user_id, 'release', p_reservation_id, v_released, -v_released);
    END IF;
    RETURN to_jsonb(v_reservation) || jsonb_build_object('idempotent', false);
END;
$$;

CREATE OR REPLACE FUNCTION public.gabriel_credit_mark_uncertain(
    p_authenticated_user_id text,
    p_user_id text,
    p_reservation_id uuid,
    p_uncertain_provider_micros bigint
) RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
    v_reservation public.gabriel_credit_reservations%ROWTYPE;
BEGIN
    PERFORM public.gabriel_credit_assert_actor(p_authenticated_user_id, p_user_id);
    SELECT * INTO v_reservation FROM public.gabriel_credit_reservations
     WHERE reservation_id = p_reservation_id AND user_id = p_user_id FOR UPDATE;
    IF NOT FOUND THEN RAISE EXCEPTION 'reservation not found'; END IF;
    IF p_uncertain_provider_micros < 0
       OR p_uncertain_provider_micros > v_reservation.provider_budget_micros THEN
        RAISE EXCEPTION 'uncertain provider amount exceeds reservation';
    END IF;
    IF v_reservation.status = 'uncertain' THEN
        IF v_reservation.uncertain_provider_micros <> p_uncertain_provider_micros THEN
            RAISE EXCEPTION 'uncertain state idempotency conflict';
        END IF;
        RETURN to_jsonb(v_reservation) || jsonb_build_object('idempotent', true);
    END IF;
    IF v_reservation.status NOT IN ('reserved', 'running') THEN
        RAISE EXCEPTION 'reservation cannot become uncertain';
    END IF;
    UPDATE public.gabriel_credit_reservations
       SET status = 'uncertain',
           uncertain_provider_micros = p_uncertain_provider_micros,
           updated_at = now()
     WHERE reservation_id = p_reservation_id RETURNING * INTO v_reservation;
    INSERT INTO public.gabriel_credit_ledger (
        user_id, event_type, reservation_id, provider_micros
    ) VALUES (p_user_id, 'uncertain', p_reservation_id, p_uncertain_provider_micros);
    RETURN to_jsonb(v_reservation) || jsonb_build_object('idempotent', false);
END;
$$;

CREATE OR REPLACE FUNCTION public.gabriel_credit_expire_grants(
    p_cutoff timestamptz DEFAULT now()
) RETURNS bigint
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
    v_grant public.gabriel_credit_grants%ROWTYPE;
    v_count bigint := 0;
BEGIN
    FOR v_grant IN
        SELECT * FROM public.gabriel_credit_grants
         WHERE expires_at IS NOT NULL AND expires_at <= p_cutoff
           AND remaining_credits > 0
         ORDER BY user_id, expires_at, grant_id FOR UPDATE
    LOOP
        UPDATE public.gabriel_credit_grants
           SET remaining_credits = 0 WHERE grant_id = v_grant.grant_id;
        UPDATE public.gabriel_credit_accounts
           SET available_credits = available_credits - v_grant.remaining_credits,
               updated_at = now() WHERE user_id = v_grant.user_id;
        INSERT INTO public.gabriel_credit_ledger (
            user_id, event_type, grant_id, delta_available
        ) VALUES (
            v_grant.user_id, 'expire', v_grant.grant_id,
            -v_grant.remaining_credits
        );
        v_count := v_count + 1;
    END LOOP;
    RETURN v_count;
END;
$$;

ALTER TABLE public.gabriel_credit_accounts ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.gabriel_credit_grants ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.gabriel_credit_legacy_snapshots ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.gabriel_credit_reservations ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.gabriel_credit_allocations ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.gabriel_credit_provider_usage ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.gabriel_credit_ledger ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON TABLE public.gabriel_credit_accounts FROM anon, authenticated;
REVOKE ALL ON TABLE public.gabriel_credit_grants FROM anon, authenticated;
REVOKE ALL ON TABLE public.gabriel_credit_legacy_snapshots FROM anon, authenticated;
REVOKE ALL ON TABLE public.gabriel_credit_reservations FROM anon, authenticated;
REVOKE ALL ON TABLE public.gabriel_credit_allocations FROM anon, authenticated;
REVOKE ALL ON TABLE public.gabriel_credit_provider_usage FROM anon, authenticated;
REVOKE ALL ON TABLE public.gabriel_credit_ledger FROM anon, authenticated;

-- Internal functions are invoked only by their trigger or by SECURITY DEFINER
-- RPCs. Callers, including service_role, do not need direct EXECUTE rights.
REVOKE ALL ON FUNCTION public.gabriel_credit_ledger_immutable()
    FROM PUBLIC, anon, authenticated, service_role;
REVOKE ALL ON FUNCTION public.gabriel_credit_assert_actor(text, text)
    FROM PUBLIC, anon, authenticated, service_role;

-- Financial RPCs are backend-only. Revoke first so an idempotent re-run also
-- removes any obsolete grants before restoring the one required identity.
REVOKE ALL ON FUNCTION public.gabriel_credit_grant(text, text, bigint, text, text, timestamptz, jsonb) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.gabriel_credit_import_legacy_balance(text, text, bigint, text) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.gabriel_credit_reserve(text, text, text, text, text, bigint, bigint, text) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.gabriel_credit_record_provider_attempt(text, text, uuid, integer, text, text, bigint, text) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.gabriel_credit_settle_provider_attempt(text, text, uuid, integer, text, bigint, bigint, bigint) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.gabriel_credit_release(text, text, uuid) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.gabriel_credit_capture(text, text, uuid, bigint, bigint) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.gabriel_credit_mark_uncertain(text, text, uuid, bigint) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.gabriel_credit_expire_grants(timestamptz) FROM PUBLIC, anon, authenticated;

GRANT EXECUTE ON FUNCTION public.gabriel_credit_grant(text, text, bigint, text, text, timestamptz, jsonb) TO service_role;
GRANT EXECUTE ON FUNCTION public.gabriel_credit_import_legacy_balance(text, text, bigint, text) TO service_role;
GRANT EXECUTE ON FUNCTION public.gabriel_credit_reserve(text, text, text, text, text, bigint, bigint, text) TO service_role;
GRANT EXECUTE ON FUNCTION public.gabriel_credit_record_provider_attempt(text, text, uuid, integer, text, text, bigint, text) TO service_role;
GRANT EXECUTE ON FUNCTION public.gabriel_credit_settle_provider_attempt(text, text, uuid, integer, text, bigint, bigint, bigint) TO service_role;
GRANT EXECUTE ON FUNCTION public.gabriel_credit_release(text, text, uuid) TO service_role;
GRANT EXECUTE ON FUNCTION public.gabriel_credit_capture(text, text, uuid, bigint, bigint) TO service_role;
GRANT EXECUTE ON FUNCTION public.gabriel_credit_mark_uncertain(text, text, uuid, bigint) TO service_role;
GRANT EXECUTE ON FUNCTION public.gabriel_credit_expire_grants(timestamptz) TO service_role;

-- No automatic backfill is intentionally included. A future, separately
-- approved migration must read gabriel_users.credits and call
-- gabriel_credit_import_legacy_balance once per user with a stable snapshot key.

COMMIT;
