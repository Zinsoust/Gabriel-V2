from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import re
import sqlite3
import time

import pytest

from core.credit_ledger import InvalidLedgerState, SQLiteCreditLedger


USER = "expiration-fix-user"
FIX_MIGRATION_PATH = (
    Path(__file__).parents[1]
    / "supabase"
    / "20261026_credit_ledger_expiration_fix.sql"
)


@pytest.fixture
def ledger(tmp_path):
    return SQLiteCreditLedger(tmp_path / "expiration-fix.sqlite3")


def _grant_and_reserve(
    ledger,
    *,
    expires_at,
    key="expiration-reservation",
    credits=40,
):
    ledger.grant(
        authenticated_user_id=USER,
        user_id=USER,
        credits=100,
        source_type="adjustment",
        source_key=f"grant-{key}",
        expires_at=expires_at,
    )
    return ledger.reserve(
        authenticated_user_id=USER,
        user_id=USER,
        operation_type="expiration-regression",
        idempotency_key=key,
        request_hash=f"hash-{key}",
        credits=credits,
        provider_budget_micros=1_000,
        pricing_version="expiration-fix-v1",
    )


def _settle_provider(ledger, reservation_id):
    ledger.record_provider_attempt(
        authenticated_user_id=USER,
        user_id=USER,
        reservation_id=reservation_id,
        attempt_no=1,
        provider="fixture-provider",
        model="fixture-model",
        max_cost_micros=1_000,
        provider_request_id=f"provider-{reservation_id}",
    )
    ledger.settle_provider_attempt(
        authenticated_user_id=USER,
        user_id=USER,
        reservation_id=reservation_id,
        attempt_no=1,
        state="succeeded",
        actual_cost_micros=500,
        input_tokens=10,
        output_tokens=5,
    )


def _rows(ledger):
    connection = ledger._connect()
    try:
        grant = connection.execute("SELECT * FROM credit_grants").fetchone()
        allocation = connection.execute("SELECT * FROM credit_allocations").fetchone()
        return dict(grant), dict(allocation)
    finally:
        connection.close()


def _assert_single_grant_ledger_consistency(ledger):
    account = ledger.get_account(USER)
    grant, allocation = _rows(ledger)
    events = ledger.ledger_events(USER)
    assert account["available_credits"] == grant["remaining_credits"]
    assert account["reserved_credits"] == grant["reserved_credits"]
    assert sum(event["delta_available"] for event in events) == account[
        "available_credits"
    ]
    assert sum(event["delta_reserved"] for event in events) == account[
        "reserved_credits"
    ]
    assert sum(event["delta_consumed"] for event in events) == account[
        "lifetime_captured"
    ]
    assert (
        allocation["captured_credits"]
        + allocation["released_credits"]
        + allocation["expired_credits"]
        == allocation["reserved_credits"]
    )
    assert min(
        account["available_credits"],
        account["reserved_credits"],
        grant["remaining_credits"],
        grant["reserved_credits"],
    ) >= 0


def test_release_before_expiration_returns_credits_once(ledger):
    reservation = _grant_and_reserve(
        ledger,
        expires_at=datetime.now(timezone.utc) + timedelta(days=1),
    )
    first = ledger.release(
        authenticated_user_id=USER,
        user_id=USER,
        reservation_id=reservation["reservation_id"],
    )
    event_count = len(ledger.ledger_events(USER))
    repeated = ledger.release(
        authenticated_user_id=USER,
        user_id=USER,
        reservation_id=reservation["reservation_id"],
    )

    account = ledger.get_account(USER)
    grant, allocation = _rows(ledger)
    assert first["idempotent"] is False
    assert repeated["idempotent"] is True
    assert len(ledger.ledger_events(USER)) == event_count
    assert account["available_credits"] == 100
    assert account["reserved_credits"] == 0
    assert grant["expired_at"] is None
    assert allocation["released_credits"] == 40
    assert allocation["expired_credits"] == 0
    _assert_single_grant_ledger_consistency(ledger)


def test_release_after_administrative_cutoff_never_restores_expired_credits(ledger):
    expiry = datetime.now(timezone.utc) + timedelta(days=1)
    reservation = _grant_and_reserve(ledger, expires_at=expiry)
    assert ledger.expire_grants(
        now=expiry + timedelta(hours=1),
        future_cutoff_approval="test:release-administrative-cutoff",
    ) == 1
    assert ledger.expire_grants(
        now=expiry + timedelta(days=1),
        future_cutoff_approval="test:release-repeat",
    ) == 0

    ledger.release(
        authenticated_user_id=USER,
        user_id=USER,
        reservation_id=reservation["reservation_id"],
    )
    account = ledger.get_account(USER)
    grant, allocation = _rows(ledger)
    assert account["available_credits"] == 0
    assert account["reserved_credits"] == 0
    assert grant["remaining_credits"] == 0
    assert grant["reserved_credits"] == 0
    assert grant["expired_at"] is not None
    assert grant["expiration_cutoff"] is not None
    assert allocation["released_credits"] == 0
    assert allocation["expired_credits"] == 40
    _assert_single_grant_ledger_consistency(ledger)


def test_partial_capture_before_expiration_releases_active_remainder(ledger):
    reservation = _grant_and_reserve(
        ledger,
        expires_at=datetime.now(timezone.utc) + timedelta(days=1),
    )
    _settle_provider(ledger, reservation["reservation_id"])
    ledger.capture(
        authenticated_user_id=USER,
        user_id=USER,
        reservation_id=reservation["reservation_id"],
        captured_credits=10,
        provider_spent_micros=500,
    )

    account = ledger.get_account(USER)
    _grant, allocation = _rows(ledger)
    assert account["available_credits"] == 90
    assert account["reserved_credits"] == 0
    assert account["lifetime_captured"] == 10
    assert allocation["captured_credits"] == 10
    assert allocation["released_credits"] == 30
    assert allocation["expired_credits"] == 0
    _assert_single_grant_ledger_consistency(ledger)


def test_partial_capture_after_administrative_cutoff_expires_remainder(ledger):
    expiry = datetime.now(timezone.utc) + timedelta(days=1)
    reservation = _grant_and_reserve(ledger, expires_at=expiry)
    _settle_provider(ledger, reservation["reservation_id"])
    assert ledger.expire_grants(
        now=expiry + timedelta(hours=1),
        future_cutoff_approval="test:capture-administrative-cutoff",
    ) == 1

    first = ledger.capture(
        authenticated_user_id=USER,
        user_id=USER,
        reservation_id=reservation["reservation_id"],
        captured_credits=10,
        provider_spent_micros=500,
    )
    event_count = len(ledger.ledger_events(USER))
    repeated = ledger.capture(
        authenticated_user_id=USER,
        user_id=USER,
        reservation_id=reservation["reservation_id"],
        captured_credits=10,
        provider_spent_micros=500,
    )

    account = ledger.get_account(USER)
    grant, allocation = _rows(ledger)
    assert first["idempotent"] is False
    assert repeated["idempotent"] is True
    assert len(ledger.ledger_events(USER)) == event_count
    assert account["available_credits"] == 0
    assert account["reserved_credits"] == 0
    assert account["lifetime_captured"] == 10
    assert grant["remaining_credits"] == 0
    assert allocation["captured_credits"] == 10
    assert allocation["released_credits"] == 0
    assert allocation["expired_credits"] == 30
    _assert_single_grant_ledger_consistency(ledger)


@pytest.mark.parametrize("final_action", ["release", "capture"])
def test_real_clock_expiration_is_persisted_during_finalisation(ledger, final_action):
    expires_at = datetime.now(timezone.utc) + timedelta(seconds=2)
    reservation = _grant_and_reserve(
        ledger,
        expires_at=expires_at,
        key=f"real-clock-{final_action}",
    )
    account_before = ledger.get_account(USER)
    grant_before, allocation_before = _rows(ledger)
    reserved_at = datetime.fromisoformat(reservation["created_at"])

    assert reservation["status"] == "reserved"
    assert reservation["quoted_credits"] == 40
    assert reserved_at < expires_at
    assert grant_before["expired_at"] is None
    assert grant_before["remaining_credits"] == 60
    assert grant_before["reserved_credits"] == 40
    assert allocation_before["reserved_credits"] == 40
    assert allocation_before["captured_credits"] == 0
    assert allocation_before["released_credits"] == 0
    assert allocation_before["expired_credits"] == 0
    assert account_before["available_credits"] == 60
    assert account_before["reserved_credits"] == 40

    if final_action == "capture":
        _settle_provider(ledger, reservation["reservation_id"])

    wait_deadline = time.monotonic() + 5
    while datetime.now(timezone.utc) <= expires_at:
        if time.monotonic() >= wait_deadline:
            pytest.fail("expires_at was not reached within the bounded wait")
        remaining = (expires_at - datetime.now(timezone.utc)).total_seconds()
        time.sleep(min(0.05, max(0.001, remaining)))
    assert datetime.now(timezone.utc) > expires_at

    if final_action == "release":
        ledger.release(
            authenticated_user_id=USER,
            user_id=USER,
            reservation_id=reservation["reservation_id"],
        )
        expected_expired = 40
    else:
        ledger.capture(
            authenticated_user_id=USER,
            user_id=USER,
            reservation_id=reservation["reservation_id"],
            captured_credits=10,
            provider_spent_micros=500,
        )
        expected_expired = 30

    account = ledger.get_account(USER)
    grant, allocation = _rows(ledger)
    assert account["available_credits"] == 0
    assert account["reserved_credits"] == 0
    assert grant["expired_at"] is not None
    assert grant["expiration_cutoff"] is not None
    assert grant["remaining_credits"] == 0
    assert allocation["expired_credits"] == expected_expired
    _assert_single_grant_ledger_consistency(ledger)


@pytest.mark.parametrize("final_action", ["release", "capture"])
def test_finalisation_rechecks_clock_after_waiting_for_write_lock(ledger, final_action):
    reservation = _grant_and_reserve(
        ledger,
        expires_at=datetime.now(timezone.utc) + timedelta(milliseconds=200),
        key=f"lock-wait-{final_action}",
    )
    if final_action == "capture":
        _settle_provider(ledger, reservation["reservation_id"])

    blocker = ledger._connect()
    blocker.execute("BEGIN IMMEDIATE")
    try:
        with ThreadPoolExecutor(max_workers=1) as pool:
            if final_action == "release":
                pending = pool.submit(
                    ledger.release,
                    authenticated_user_id=USER,
                    user_id=USER,
                    reservation_id=reservation["reservation_id"],
                )
                expected_expired = 40
            else:
                pending = pool.submit(
                    ledger.capture,
                    authenticated_user_id=USER,
                    user_id=USER,
                    reservation_id=reservation["reservation_id"],
                    captured_credits=10,
                    provider_spent_micros=500,
                )
                expected_expired = 30
            time.sleep(0.35)
            blocker.commit()
            result = pending.result(timeout=5)
    finally:
        blocker.close()

    assert result["idempotent"] is False
    account = ledger.get_account(USER)
    grant, allocation = _rows(ledger)
    assert account["available_credits"] == 0
    assert account["reserved_credits"] == 0
    assert grant["expired_at"] is not None
    assert allocation["expired_credits"] == expected_expired
    _assert_single_grant_ledger_consistency(ledger)


def test_future_cutoff_requires_explicit_approval_and_records_it(ledger):
    expiry = datetime.now(timezone.utc) + timedelta(hours=1)
    _grant_and_reserve(ledger, expires_at=expiry, key="future-cutoff-guard")

    with pytest.raises(InvalidLedgerState, match="explicit approval"):
        ledger.expire_grants(now=expiry + timedelta(hours=1))

    approval = "test:approved-future-cutoff"
    assert ledger.expire_grants(
        now=expiry + timedelta(hours=1),
        future_cutoff_approval=approval,
    ) == 1
    expiration_events = [
        event for event in ledger.ledger_events(USER)
        if event["event_type"] == "expire"
    ]
    assert expiration_events
    metadata = json.loads(expiration_events[0]["metadata"])
    assert metadata["future_cutoff_approval"] == approval


def test_concurrent_releases_after_expiration_create_one_finalisation(ledger):
    expiry = datetime.now(timezone.utc) + timedelta(days=1)
    reservation = _grant_and_reserve(ledger, expires_at=expiry)
    assert ledger.expire_grants(
        now=expiry + timedelta(hours=1),
        future_cutoff_approval="test:concurrent-release",
    ) == 1

    def release_once(_index):
        return ledger.release(
            authenticated_user_id=USER,
            user_id=USER,
            reservation_id=reservation["reservation_id"],
        )

    with ThreadPoolExecutor(max_workers=20) as pool:
        results = list(pool.map(release_once, range(20)))

    assert sum(not result["idempotent"] for result in results) == 1
    assert sum(result["idempotent"] for result in results) == 19
    events = ledger.ledger_events(USER)
    assert [event["event_type"] for event in events].count("release") == 1
    assert [event["event_type"] for event in events].count("expire") == 2
    assert ledger.get_account(USER)["available_credits"] == 0
    _assert_single_grant_ledger_consistency(ledger)


def test_expiration_racing_release_cannot_leave_expired_credits_available(ledger):
    expiry = datetime.now(timezone.utc) + timedelta(days=1)
    reservation = _grant_and_reserve(ledger, expires_at=expiry)

    with ThreadPoolExecutor(max_workers=2) as pool:
        expiration = pool.submit(
            ledger.expire_grants,
            now=expiry + timedelta(hours=1),
            future_cutoff_approval="test:expiration-release-race",
        )
        release = pool.submit(
            ledger.release,
            authenticated_user_id=USER,
            user_id=USER,
            reservation_id=reservation["reservation_id"],
        )
        assert expiration.result() == 1
        assert release.result()["status"] == "released"

    account = ledger.get_account(USER)
    grant, allocation = _rows(ledger)
    assert account["available_credits"] == 0
    assert account["reserved_credits"] == 0
    assert grant["remaining_credits"] == 0
    assert grant["expired_at"] is not None
    assert allocation["captured_credits"] == 0
    assert allocation["released_credits"] + allocation["expired_credits"] == 40
    _assert_single_grant_ledger_consistency(ledger)


def test_corrective_migration_is_additive_and_preserves_security_contract():
    migration = FIX_MIGRATION_PATH.read_text(encoding="utf-8").lower()
    compact = re.sub(r"\s+", " ", migration)
    assert re.search(r"(?m)^begin;$", migration)
    assert migration.rstrip().endswith("commit;")
    assert "add column if not exists expired_at" in migration
    assert "add column if not exists expiration_cutoff" in migration
    assert "add column if not exists expired_credits" in migration
    assert "update public.gabriel_credit_grants" in migration
    assert "update public.gabriel_credit_ledger" not in migration
    assert "delete from public.gabriel_credit_ledger" not in migration
    assert "disable row level security" not in migration
    assert "create policy" not in migration
    assert "set search_path = pg_catalog, pg_temp" in migration
    assert migration.count("security definer") == 3
    assert migration.count("for update of allocation, credit_grant;") == 2
    for function_name in ("gabriel_credit_release", "gabriel_credit_capture"):
        function_start = migration.index(
            f"create or replace function public.{function_name}"
        )
        function_end = migration.index("$$;", function_start)
        function_body = migration[function_start:function_end]
        assert function_body.index(
            "for update of allocation, credit_grant;"
        ) < function_body.index("v_finalise_time := clock_timestamp();")
    assert "gabriel.credit_expiration_future_cutoff_approval" in migration
    assert "where role.rolname = session_user" in migration
    assert "coalesce(v_session_is_superuser, false) is not true" in migration
    assert "errcode = '42501'" in migration
    for signature in (
        "gabriel_credit_release(text, text, uuid)",
        "gabriel_credit_capture( text, text, uuid, bigint, bigint )",
        "gabriel_credit_expire_grants(timestamptz)",
    ):
        assert f"grant execute on function public.{signature} to service_role;" in compact
    assert not re.search(
        r"grant\s+.+?\s+on\s+(?:table\s+)?public\.gabriel_credit_.+?"
        r"\s+to\s+(public|anon|authenticated)\b",
        migration,
        flags=re.DOTALL,
    )
    assert "from public, anon, authenticated" in compact
    assert "gabriel_users" not in migration


def test_existing_sqlite_phase1_file_is_upgraded_without_rewriting_history(tmp_path):
    database_path = tmp_path / "phase1-existing.sqlite3"
    connection = sqlite3.connect(database_path)
    try:
        connection.executescript(
            """
            PRAGMA foreign_keys = ON;
            CREATE TABLE credit_accounts (
                user_id TEXT PRIMARY KEY,
                available_credits INTEGER NOT NULL DEFAULT 0,
                reserved_credits INTEGER NOT NULL DEFAULT 0,
                lifetime_granted INTEGER NOT NULL DEFAULT 0,
                lifetime_captured INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE credit_grants (
                grant_id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL REFERENCES credit_accounts(user_id),
                source_type TEXT NOT NULL,
                source_key TEXT NOT NULL,
                granted_credits INTEGER NOT NULL,
                remaining_credits INTEGER NOT NULL,
                reserved_credits INTEGER NOT NULL DEFAULT 0,
                starts_at TEXT NOT NULL,
                expires_at TEXT,
                metadata TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL,
                UNIQUE (user_id, source_key)
            );
            CREATE TABLE credit_reservations (
                reservation_id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL REFERENCES credit_accounts(user_id),
                operation_type TEXT NOT NULL,
                idempotency_key TEXT NOT NULL,
                request_hash TEXT NOT NULL,
                pricing_version TEXT NOT NULL,
                quoted_credits INTEGER NOT NULL,
                provider_budget_micros INTEGER NOT NULL,
                provider_spent_micros INTEGER NOT NULL DEFAULT 0,
                uncertain_provider_micros INTEGER NOT NULL DEFAULT 0,
                captured_credits INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                finalised_at TEXT,
                UNIQUE (user_id, idempotency_key)
            );
            CREATE TABLE credit_allocations (
                reservation_id TEXT NOT NULL REFERENCES credit_reservations(reservation_id),
                grant_id TEXT NOT NULL REFERENCES credit_grants(grant_id),
                reserved_credits INTEGER NOT NULL,
                captured_credits INTEGER NOT NULL DEFAULT 0,
                released_credits INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (reservation_id, grant_id)
            );
            CREATE TABLE credit_ledger_events (
                sequence_no INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id TEXT NOT NULL UNIQUE,
                user_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                grant_id TEXT,
                reservation_id TEXT,
                delta_available INTEGER NOT NULL DEFAULT 0,
                delta_reserved INTEGER NOT NULL DEFAULT 0,
                delta_consumed INTEGER NOT NULL DEFAULT 0,
                provider_micros INTEGER NOT NULL DEFAULT 0,
                metadata TEXT NOT NULL DEFAULT '{}',
                created_at TEXT NOT NULL
            );
            INSERT INTO credit_accounts VALUES (
                'existing-user', 0, 0, 7, 0,
                '2026-01-01T00:00:00+00:00', '2026-01-02T00:00:00+00:00'
            );
            INSERT INTO credit_grants VALUES (
                'existing-grant', 'existing-user', 'adjustment', 'existing-source',
                7, 0, 0, '2026-01-01T00:00:00+00:00',
                '2026-01-02T00:00:00+00:00', '{}',
                '2026-01-01T00:00:00+00:00'
            );
            INSERT INTO credit_ledger_events (
                event_id, user_id, event_type, grant_id, delta_available, created_at
            ) VALUES (
                'existing-event', 'existing-user', 'expire', 'existing-grant', -7,
                '2026-01-02T00:00:01+00:00'
            );
            """
        )
        connection.commit()
    finally:
        connection.close()

    upgraded = SQLiteCreditLedger(database_path)
    connection = upgraded._connect()
    try:
        grant_columns = {
            row["name"] for row in connection.execute("PRAGMA table_info(credit_grants)")
        }
        allocation_columns = {
            row["name"]
            for row in connection.execute("PRAGMA table_info(credit_allocations)")
        }
        grant = connection.execute(
            "SELECT * FROM credit_grants WHERE grant_id = 'existing-grant'"
        ).fetchone()
        event_count = connection.execute(
            "SELECT count(*) AS total FROM credit_ledger_events"
        ).fetchone()["total"]
    finally:
        connection.close()

    assert {"expired_at", "expiration_cutoff"} <= grant_columns
    assert "expired_credits" in allocation_columns
    assert grant["expired_at"] == "2026-01-02T00:00:01+00:00"
    assert grant["expiration_cutoff"] == "2026-01-02T00:00:00+00:00"
    assert event_count == 1
    assert upgraded.get_account("existing-user")["lifetime_granted"] == 7


def test_feature_flag_remains_disabled_by_default():
    assert SQLiteCreditLedger
    from core.credit_ledger import credit_ledger_enabled

    assert credit_ledger_enabled({}) is False
