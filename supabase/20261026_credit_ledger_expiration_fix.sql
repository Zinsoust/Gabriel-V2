-- Gabriel V3 - P0 correction: expired reserved credits must never reappear.
-- Additive migration. Apply only after 20261024_credit_ledger_phase1.sql.
-- A cutoff is authoritative and irreversible. Production schedulers must pass
-- clock_timestamp(); a future cutoff is reserved for explicitly approved
-- administrative operations and isolated certification tests.

BEGIN;

ALTER TABLE public.gabriel_credit_grants
    ADD COLUMN IF NOT EXISTS expired_at timestamptz;
ALTER TABLE public.gabriel_credit_grants
    ADD COLUMN IF NOT EXISTS expiration_cutoff timestamptz;
ALTER TABLE public.gabriel_credit_allocations
    ADD COLUMN IF NOT EXISTS expired_credits bigint NOT NULL DEFAULT 0
        CHECK (expired_credits >= 0);

DO $constraints$
BEGIN
    IF NOT EXISTS (
        SELECT 1
          FROM pg_catalog.pg_constraint
         WHERE conrelid = 'public.gabriel_credit_grants'::pg_catalog.regclass
           AND conname = 'gabriel_credit_grants_expiration_state_check'
    ) THEN
        ALTER TABLE public.gabriel_credit_grants
            ADD CONSTRAINT gabriel_credit_grants_expiration_state_check
            CHECK (
                (expired_at IS NULL AND expiration_cutoff IS NULL)
                OR
                (
                    expired_at IS NOT NULL
                    AND expiration_cutoff IS NOT NULL
                    AND expires_at IS NOT NULL
                    AND expiration_cutoff >= expires_at
                )
            ) NOT VALID;
        ALTER TABLE public.gabriel_credit_grants
            VALIDATE CONSTRAINT gabriel_credit_grants_expiration_state_check;
    END IF;

    IF NOT EXISTS (
        SELECT 1
          FROM pg_catalog.pg_constraint
         WHERE conrelid = 'public.gabriel_credit_allocations'::pg_catalog.regclass
           AND conname = 'gabriel_credit_allocations_finalisation_check'
    ) THEN
        ALTER TABLE public.gabriel_credit_allocations
            ADD CONSTRAINT gabriel_credit_allocations_finalisation_check
            CHECK (
                captured_credits + released_credits + expired_credits
                <= reserved_credits
            ) NOT VALID;
        ALTER TABLE public.gabriel_credit_allocations
            VALIDATE CONSTRAINT gabriel_credit_allocations_finalisation_check;
    END IF;
END
$constraints$;

-- Phase 1 already emitted append-only expire events for available credits.
-- Backfill only the newly added state columns; never rewrite balances/events.
WITH first_expiration AS (
    SELECT grant_id, min(created_at) AS expired_at
      FROM public.gabriel_credit_ledger
     WHERE event_type = 'expire' AND grant_id IS NOT NULL
     GROUP BY grant_id
)
UPDATE public.gabriel_credit_grants AS credit_grant
   SET expired_at = first_expiration.expired_at,
       expiration_cutoff = credit_grant.expires_at
  FROM first_expiration
 WHERE credit_grant.grant_id = first_expiration.grant_id
   AND credit_grant.expired_at IS NULL;

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
    v_item record;
    v_finalise_time timestamptz;
    v_released bigint;
    v_expired bigint;
    v_released_total bigint := 0;
    v_expired_total bigint := 0;
    v_available_expired bigint;
    v_newly_expired boolean;
BEGIN
    PERFORM public.gabriel_credit_assert_actor(
        p_authenticated_user_id, p_user_id
    );
    SELECT * INTO v_reservation
      FROM public.gabriel_credit_reservations
     WHERE reservation_id = p_reservation_id AND user_id = p_user_id
     FOR UPDATE;
    IF NOT FOUND THEN RAISE EXCEPTION 'reservation not found'; END IF;
    IF v_reservation.status = 'released' THEN
        RETURN to_jsonb(v_reservation) || jsonb_build_object('idempotent', true);
    END IF;
    IF v_reservation.status <> 'reserved'
       OR EXISTS (
           SELECT 1 FROM public.gabriel_credit_provider_usage
            WHERE reservation_id = p_reservation_id
       ) THEN
        RAISE EXCEPTION 'only a never-started reservation can be released';
    END IF;

    -- Account -> grant lock order matches reserve/expire and prevents a stale
    -- release racing an authoritative expiration. Lock every allocation/grant
    -- before choosing the single financial linearisation timestamp.
    PERFORM 1 FROM public.gabriel_credit_accounts
     WHERE user_id = p_user_id FOR UPDATE;
    PERFORM 1
      FROM public.gabriel_credit_allocations AS allocation
      JOIN public.gabriel_credit_grants AS credit_grant
        ON credit_grant.grant_id = allocation.grant_id
     WHERE allocation.reservation_id = p_reservation_id
     ORDER BY credit_grant.expires_at ASC NULLS LAST,
              credit_grant.created_at, credit_grant.grant_id
     FOR UPDATE OF allocation, credit_grant;
    v_finalise_time := clock_timestamp();

    FOR v_item IN
        SELECT allocation.*,
               credit_grant.expires_at AS grant_expires_at,
               credit_grant.expired_at AS grant_expired_at,
               credit_grant.expiration_cutoff AS grant_expiration_cutoff,
               credit_grant.remaining_credits AS grant_remaining_credits,
               credit_grant.reserved_credits AS grant_reserved_credits,
               credit_grant.created_at AS grant_created_at
          FROM public.gabriel_credit_allocations AS allocation
          JOIN public.gabriel_credit_grants AS credit_grant
            ON credit_grant.grant_id = allocation.grant_id
         WHERE allocation.reservation_id = p_reservation_id
         ORDER BY credit_grant.expires_at ASC NULLS LAST,
                  credit_grant.created_at, credit_grant.grant_id
    LOOP
        v_newly_expired := false;
        v_available_expired := 0;
        IF v_item.grant_expired_at IS NULL
           AND v_item.grant_expires_at IS NOT NULL
           AND v_item.grant_expires_at <= v_finalise_time THEN
            v_newly_expired := true;
            v_available_expired := v_item.grant_remaining_credits;
            UPDATE public.gabriel_credit_grants
               SET remaining_credits = 0,
                   expired_at = v_finalise_time,
                   expiration_cutoff = v_finalise_time
             WHERE grant_id = v_item.grant_id;
            UPDATE public.gabriel_credit_accounts
               SET available_credits = available_credits - v_available_expired,
                   updated_at = v_finalise_time
             WHERE user_id = p_user_id;
            INSERT INTO public.gabriel_credit_ledger (
                user_id, event_type, grant_id, delta_available, metadata
            ) VALUES (
                p_user_id, 'expire', v_item.grant_id, -v_available_expired,
                jsonb_build_object(
                    'phase', 'grant_expiration',
                    'cutoff', v_finalise_time,
                    'available_expired', v_available_expired,
                    'reserved_at_expiration', v_item.grant_reserved_credits
                )
            );
        END IF;

        v_expired := CASE
            WHEN v_item.grant_expired_at IS NOT NULL OR v_newly_expired
            THEN v_item.reserved_credits ELSE 0
        END;
        v_released := v_item.reserved_credits - v_expired;
        v_expired_total := v_expired_total + v_expired;
        v_released_total := v_released_total + v_released;

        UPDATE public.gabriel_credit_allocations
           SET captured_credits = 0,
               released_credits = v_released,
               expired_credits = v_expired
         WHERE reservation_id = p_reservation_id
           AND grant_id = v_item.grant_id;
        UPDATE public.gabriel_credit_grants
           SET reserved_credits = reserved_credits - v_item.reserved_credits,
               remaining_credits = remaining_credits + v_released
         WHERE grant_id = v_item.grant_id;

        IF v_expired > 0 THEN
            INSERT INTO public.gabriel_credit_ledger (
                user_id, event_type, grant_id, reservation_id,
                delta_reserved, metadata
            ) VALUES (
                p_user_id, 'expire', v_item.grant_id, p_reservation_id,
                -v_expired,
                jsonb_build_object(
                    'phase', 'reserved_finalisation',
                    'final_status', 'released',
                    'reserved_expired', v_expired,
                    'expiration_cutoff', coalesce(
                        v_item.grant_expiration_cutoff, v_finalise_time
                    )
                )
            );
        END IF;
    END LOOP;

    IF v_released_total + v_expired_total <> v_reservation.quoted_credits THEN
        RAISE EXCEPTION 'allocation finalisation does not conserve credits';
    END IF;
    UPDATE public.gabriel_credit_accounts
       SET available_credits = available_credits + v_released_total,
           reserved_credits = reserved_credits - v_reservation.quoted_credits,
           updated_at = v_finalise_time
     WHERE user_id = p_user_id;
    UPDATE public.gabriel_credit_reservations
       SET status = 'released', finalised_at = v_finalise_time,
           updated_at = v_finalise_time
     WHERE reservation_id = p_reservation_id
     RETURNING * INTO v_reservation;
    INSERT INTO public.gabriel_credit_ledger (
        user_id, event_type, reservation_id,
        delta_available, delta_reserved, metadata
    ) VALUES (
        p_user_id, 'release', p_reservation_id,
        v_released_total, -v_released_total,
        jsonb_build_object(
            'returned_to_available', v_released_total,
            'expired_instead_of_released', v_expired_total
        )
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
    v_item record;
    v_capture bigint;
    v_alloc_capture bigint;
    v_alloc_release bigint;
    v_alloc_expire bigint;
    v_remaining_capture bigint;
    v_released_total bigint := 0;
    v_expired_total bigint := 0;
    v_attempts bigint;
    v_billable_ceiling bigint;
    v_pending_attempts bigint;
    v_finalise_time timestamptz;
    v_available_expired bigint;
    v_newly_expired boolean;
BEGIN
    PERFORM public.gabriel_credit_assert_actor(
        p_authenticated_user_id, p_user_id
    );
    SELECT * INTO v_reservation
      FROM public.gabriel_credit_reservations
     WHERE reservation_id = p_reservation_id AND user_id = p_user_id
     FOR UPDATE;
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
        RAISE EXCEPTION 'reservation cannot be captured from state %',
            v_reservation.status;
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

    PERFORM 1 FROM public.gabriel_credit_accounts
     WHERE user_id = p_user_id FOR UPDATE;
    -- Lock the complete allocation set before choosing the capture
    -- linearisation timestamp. No expiry decision uses a pre-lock clock.
    PERFORM 1
      FROM public.gabriel_credit_allocations AS allocation
      JOIN public.gabriel_credit_grants AS credit_grant
        ON credit_grant.grant_id = allocation.grant_id
     WHERE allocation.reservation_id = p_reservation_id
     ORDER BY credit_grant.expires_at ASC NULLS LAST,
              credit_grant.created_at, credit_grant.grant_id
     FOR UPDATE OF allocation, credit_grant;
    v_finalise_time := clock_timestamp();
    v_remaining_capture := v_capture;
    FOR v_item IN
        SELECT allocation.*,
               credit_grant.expires_at AS grant_expires_at,
               credit_grant.expired_at AS grant_expired_at,
               credit_grant.expiration_cutoff AS grant_expiration_cutoff,
               credit_grant.remaining_credits AS grant_remaining_credits,
               credit_grant.reserved_credits AS grant_reserved_credits,
               credit_grant.created_at AS grant_created_at
          FROM public.gabriel_credit_allocations AS allocation
          JOIN public.gabriel_credit_grants AS credit_grant
            ON credit_grant.grant_id = allocation.grant_id
         WHERE allocation.reservation_id = p_reservation_id
         ORDER BY credit_grant.expires_at ASC NULLS LAST,
                  credit_grant.created_at, credit_grant.grant_id
    LOOP
        v_newly_expired := false;
        v_available_expired := 0;
        IF v_item.grant_expired_at IS NULL
           AND v_item.grant_expires_at IS NOT NULL
           AND v_item.grant_expires_at <= v_finalise_time THEN
            v_newly_expired := true;
            v_available_expired := v_item.grant_remaining_credits;
            UPDATE public.gabriel_credit_grants
               SET remaining_credits = 0,
                   expired_at = v_finalise_time,
                   expiration_cutoff = v_finalise_time
             WHERE grant_id = v_item.grant_id;
            UPDATE public.gabriel_credit_accounts
               SET available_credits = available_credits - v_available_expired,
                   updated_at = v_finalise_time
             WHERE user_id = p_user_id;
            INSERT INTO public.gabriel_credit_ledger (
                user_id, event_type, grant_id, delta_available, metadata
            ) VALUES (
                p_user_id, 'expire', v_item.grant_id, -v_available_expired,
                jsonb_build_object(
                    'phase', 'grant_expiration',
                    'cutoff', v_finalise_time,
                    'available_expired', v_available_expired,
                    'reserved_at_expiration', v_item.grant_reserved_credits
                )
            );
        END IF;

        v_alloc_capture := least(
            v_remaining_capture, v_item.reserved_credits
        );
        v_remaining_capture := v_remaining_capture - v_alloc_capture;
        IF v_item.grant_expired_at IS NOT NULL OR v_newly_expired THEN
            v_alloc_expire := v_item.reserved_credits - v_alloc_capture;
            v_alloc_release := 0;
        ELSE
            v_alloc_expire := 0;
            v_alloc_release := v_item.reserved_credits - v_alloc_capture;
        END IF;
        v_expired_total := v_expired_total + v_alloc_expire;
        v_released_total := v_released_total + v_alloc_release;

        UPDATE public.gabriel_credit_allocations
           SET captured_credits = v_alloc_capture,
               released_credits = v_alloc_release,
               expired_credits = v_alloc_expire
         WHERE reservation_id = p_reservation_id
           AND grant_id = v_item.grant_id;
        UPDATE public.gabriel_credit_grants
           SET reserved_credits = reserved_credits - v_item.reserved_credits,
               remaining_credits = remaining_credits + v_alloc_release
         WHERE grant_id = v_item.grant_id;

        IF v_alloc_expire > 0 THEN
            INSERT INTO public.gabriel_credit_ledger (
                user_id, event_type, grant_id, reservation_id,
                delta_reserved, metadata
            ) VALUES (
                p_user_id, 'expire', v_item.grant_id, p_reservation_id,
                -v_alloc_expire,
                jsonb_build_object(
                    'phase', 'reserved_finalisation',
                    'final_status', 'captured',
                    'reserved_expired', v_alloc_expire,
                    'expiration_cutoff', coalesce(
                        v_item.grant_expiration_cutoff, v_finalise_time
                    )
                )
            );
        END IF;
    END LOOP;
    IF v_remaining_capture <> 0 THEN
        RAISE EXCEPTION 'allocation total lower than capture';
    END IF;
    IF v_capture + v_released_total + v_expired_total
       <> v_reservation.quoted_credits THEN
        RAISE EXCEPTION 'allocation finalisation does not conserve credits';
    END IF;

    UPDATE public.gabriel_credit_accounts
       SET available_credits = available_credits + v_released_total,
           reserved_credits = reserved_credits - v_reservation.quoted_credits,
           lifetime_captured = lifetime_captured + v_capture,
           updated_at = v_finalise_time
     WHERE user_id = p_user_id;
    UPDATE public.gabriel_credit_reservations
       SET status = 'captured', captured_credits = v_capture,
           provider_spent_micros = p_provider_spent_micros,
           uncertain_provider_micros = 0,
           finalised_at = v_finalise_time, updated_at = v_finalise_time
     WHERE reservation_id = p_reservation_id
     RETURNING * INTO v_reservation;
    IF v_capture > 0 THEN
        INSERT INTO public.gabriel_credit_ledger (
            user_id, event_type, reservation_id, delta_reserved,
            delta_consumed, provider_micros
        ) VALUES (
            p_user_id, 'capture', p_reservation_id, -v_capture,
            v_capture, p_provider_spent_micros
        );
    END IF;
    IF v_released_total > 0 THEN
        INSERT INTO public.gabriel_credit_ledger (
            user_id, event_type, reservation_id,
            delta_available, delta_reserved, metadata
        ) VALUES (
            p_user_id, 'release', p_reservation_id,
            v_released_total, -v_released_total,
            jsonb_build_object(
                'returned_to_available', v_released_total,
                'expired_instead_of_released', v_expired_total
            )
        );
    END IF;
    RETURN to_jsonb(v_reservation) || jsonb_build_object('idempotent', false);
END;
$$;

CREATE OR REPLACE FUNCTION public.gabriel_credit_expire_grants(
    p_cutoff timestamptz DEFAULT clock_timestamp()
) RETURNS bigint
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, pg_temp
AS $$
DECLARE
    v_candidate record;
    v_grant public.gabriel_credit_grants%ROWTYPE;
    v_account public.gabriel_credit_accounts%ROWTYPE;
    v_event_time timestamptz;
    v_wall_time timestamptz;
    v_future_cutoff boolean;
    v_approval_ref text;
    v_session_is_superuser boolean := false;
    v_count bigint := 0;
BEGIN
    IF p_cutoff IS NULL THEN
        RAISE EXCEPTION 'expiration cutoff is required';
    END IF;
    v_wall_time := clock_timestamp();
    v_future_cutoff := p_cutoff > v_wall_time;
    IF v_future_cutoff THEN
        v_approval_ref := nullif(btrim(current_setting(
            'gabriel.credit_expiration_future_cutoff_approval', true
        )), '');
        SELECT role.rolsuper INTO v_session_is_superuser
          FROM pg_catalog.pg_roles AS role
         WHERE role.rolname = session_user;
        IF coalesce(v_session_is_superuser, false) IS NOT TRUE
           OR v_approval_ref IS NULL
           OR length(v_approval_ref) > 200 THEN
            RAISE EXCEPTION 'future expiration cutoff requires privileged explicit approval'
                USING ERRCODE = '42501';
        END IF;
    END IF;
    FOR v_candidate IN
        SELECT grant_id, user_id, expires_at
          FROM public.gabriel_credit_grants
         WHERE expires_at IS NOT NULL
           AND expires_at <= p_cutoff
           AND expired_at IS NULL
         ORDER BY user_id, expires_at, grant_id
    LOOP
        SELECT * INTO v_account
          FROM public.gabriel_credit_accounts
         WHERE user_id = v_candidate.user_id
         FOR UPDATE;
        IF NOT FOUND THEN
            RAISE EXCEPTION 'credit account missing for grant';
        END IF;
        SELECT * INTO v_grant
          FROM public.gabriel_credit_grants
         WHERE grant_id = v_candidate.grant_id
         FOR UPDATE;
        IF NOT FOUND OR v_grant.expired_at IS NOT NULL
           OR v_grant.expires_at IS NULL
           OR v_grant.expires_at > p_cutoff THEN
            CONTINUE;
        END IF;
        IF v_account.available_credits < v_grant.remaining_credits THEN
            RAISE EXCEPTION 'account and grant balances diverged';
        END IF;

        v_event_time := clock_timestamp();
        UPDATE public.gabriel_credit_grants
           SET remaining_credits = 0,
               expired_at = v_event_time,
               expiration_cutoff = p_cutoff
         WHERE grant_id = v_grant.grant_id;
        UPDATE public.gabriel_credit_accounts
           SET available_credits = available_credits - v_grant.remaining_credits,
               updated_at = v_event_time
         WHERE user_id = v_grant.user_id;
        INSERT INTO public.gabriel_credit_ledger (
            user_id, event_type, grant_id, delta_available, metadata
        ) VALUES (
            v_grant.user_id, 'expire', v_grant.grant_id,
            -v_grant.remaining_credits,
            jsonb_build_object(
                'phase', 'grant_expiration',
                'cutoff', p_cutoff,
                'future_cutoff', v_future_cutoff,
                'future_cutoff_approval', v_approval_ref,
                'approved_by_session_user', CASE
                    WHEN v_future_cutoff THEN session_user ELSE NULL
                END,
                'available_expired', v_grant.remaining_credits,
                'reserved_at_expiration', v_grant.reserved_credits
            )
        );
        v_count := v_count + 1;
    END LOOP;
    RETURN v_count;
END;
$$;

REVOKE ALL ON FUNCTION public.gabriel_credit_release(text, text, uuid)
    FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.gabriel_credit_capture(
    text, text, uuid, bigint, bigint
) FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.gabriel_credit_expire_grants(timestamptz)
    FROM PUBLIC, anon, authenticated;

GRANT EXECUTE ON FUNCTION public.gabriel_credit_release(text, text, uuid)
    TO service_role;
GRANT EXECUTE ON FUNCTION public.gabriel_credit_capture(
    text, text, uuid, bigint, bigint
) TO service_role;
GRANT EXECUTE ON FUNCTION public.gabriel_credit_expire_grants(timestamptz)
    TO service_role;

COMMIT;
