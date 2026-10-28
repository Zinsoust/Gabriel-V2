from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
import re
import sqlite3

import pytest

from core.credit_ledger import (
    IdempotencyConflict,
    IdentityMismatch,
    InsufficientCredits,
    InvalidLedgerState,
    SQLiteCreditLedger,
    credit_ledger_enabled,
)


USER = "ledger-user-a"
MIGRATION_PATH = (
    Path(__file__).parents[1]
    / "supabase"
    / "20261024_credit_ledger_phase1.sql"
)


def _migration_sql():
    return MIGRATION_PATH.read_text(encoding="utf-8").lower()


def _function_blocks(migration):
    return {
        match.group("name"): match.group("block")
        for match in re.finditer(
            r"create or replace function public\."
            r"(?P<name>gabriel_credit_[a-z0-9_]+)"
            r"(?P<block>.*?\$\$;)",
            migration,
            flags=re.DOTALL,
        )
    }


@pytest.fixture
def ledger(tmp_path):
    return SQLiteCreditLedger(tmp_path / "credit-ledger.sqlite3")


def _grant(ledger, credits=10, source_key="fixture-grant"):
    return ledger.grant(
        authenticated_user_id=USER,
        user_id=USER,
        credits=credits,
        source_type="adjustment",
        source_key=source_key,
    )


def _reserve(ledger, *, key="request-1", request_hash="hash-1", credits=2):
    return ledger.reserve(
        authenticated_user_id=USER,
        user_id=USER,
        operation_type="test-operation",
        idempotency_key=key,
        request_hash=request_hash,
        credits=credits,
        provider_budget_micros=credits * 50_000,
    )


def _record_and_settle(ledger, reservation_id, *, actual=40_000, state="succeeded"):
    ledger.record_provider_attempt(
        authenticated_user_id=USER,
        user_id=USER,
        reservation_id=reservation_id,
        attempt_no=1,
        provider="fixture-provider",
        model="fixture-model-v1",
        max_cost_micros=100_000,
        provider_request_id=f"provider-{reservation_id}",
    )
    return ledger.settle_provider_attempt(
        authenticated_user_id=USER,
        user_id=USER,
        reservation_id=reservation_id,
        attempt_no=1,
        state=state,
        actual_cost_micros=None if state == "uncertain" else actual,
        input_tokens=None if state == "uncertain" else 100,
        output_tokens=None if state == "uncertain" else 20,
    )


def test_feature_flag_is_disabled_by_default():
    assert credit_ledger_enabled({}) is False
    assert credit_ledger_enabled({"GABRIEL_CREDIT_LEDGER_ENABLED": "false"}) is False
    assert credit_ledger_enabled({"GABRIEL_CREDIT_LEDGER_ENABLED": "true"}) is True


def test_grant_and_reservation_are_idempotent(ledger):
    first_grant = _grant(ledger)
    repeated_grant = _grant(ledger)
    assert first_grant["grant_id"] == repeated_grant["grant_id"]
    assert repeated_grant["idempotent"] is True

    first = _reserve(ledger)
    repeated = _reserve(ledger)
    assert first["reservation_id"] == repeated["reservation_id"]
    assert repeated["idempotent"] is True
    assert ledger.get_account(USER)["available_credits"] == 8
    assert [event["event_type"] for event in ledger.ledger_events(USER)] == [
        "grant",
        "reserve",
    ]


def test_idempotency_key_rejects_a_different_payload(ledger):
    _grant(ledger)
    _reserve(ledger)
    with pytest.raises(IdempotencyConflict):
        _reserve(ledger, request_hash="different-hash")
    assert ledger.get_account(USER)["available_credits"] == 8


def test_one_hundred_concurrent_requests_never_overdraw(tmp_path):
    path = tmp_path / "concurrent-credit-ledger.sqlite3"
    ledger = SQLiteCreditLedger(path)
    _grant(ledger, credits=50)

    def reserve(index):
        try:
            result = _reserve(
                ledger,
                key=f"concurrent-{index}",
                request_hash=f"hash-{index}",
                credits=1,
            )
            return result["reservation_id"]
        except InsufficientCredits:
            return None

    with ThreadPoolExecutor(max_workers=20) as pool:
        results = list(pool.map(reserve, range(100)))

    successful = [reservation_id for reservation_id in results if reservation_id]
    account = ledger.get_account(USER)
    assert len(successful) == 50
    assert len(set(successful)) == 50
    assert account["available_credits"] == 0
    assert account["reserved_credits"] == 50
    assert account["available_credits"] >= 0


def test_one_hundred_duplicate_requests_create_one_reservation(tmp_path):
    ledger = SQLiteCreditLedger(tmp_path / "duplicate-credit-ledger.sqlite3")
    _grant(ledger, credits=10)

    def reserve(_index):
        return _reserve(ledger, key="same-request", request_hash="same-hash", credits=1)

    with ThreadPoolExecutor(max_workers=20) as pool:
        results = list(pool.map(reserve, range(100)))

    assert len({result["reservation_id"] for result in results}) == 1
    assert ledger.get_account(USER)["available_credits"] == 9
    assert [event["event_type"] for event in ledger.ledger_events(USER)].count("reserve") == 1


def test_insufficient_balance_rolls_back_without_financial_event(ledger):
    _grant(ledger, credits=2)
    before = ledger.ledger_events(USER)
    with pytest.raises(InsufficientCredits):
        _reserve(ledger, credits=3)
    assert ledger.get_account(USER)["available_credits"] == 2
    assert ledger.get_account(USER)["reserved_credits"] == 0
    assert ledger.ledger_events(USER) == before


def test_release_is_only_allowed_before_provider_attempt(ledger):
    _grant(ledger)
    reservation = _reserve(ledger, credits=4)
    released = ledger.release(
        authenticated_user_id=USER,
        user_id=USER,
        reservation_id=reservation["reservation_id"],
    )
    repeated = ledger.release(
        authenticated_user_id=USER,
        user_id=USER,
        reservation_id=reservation["reservation_id"],
    )
    assert released["status"] == "released"
    assert repeated["idempotent"] is True
    assert ledger.get_account(USER)["available_credits"] == 10
    assert ledger.get_account(USER)["reserved_credits"] == 0


def test_provider_failure_can_capture_actual_cost_and_release_remainder(ledger):
    _grant(ledger)
    reservation = _reserve(ledger, credits=4)
    _record_and_settle(
        ledger,
        reservation["reservation_id"],
        actual=60_000,
        state="failed",
    )
    captured = ledger.capture(
        authenticated_user_id=USER,
        user_id=USER,
        reservation_id=reservation["reservation_id"],
        captured_credits=2,
        provider_spent_micros=60_000,
    )
    repeated = ledger.capture(
        authenticated_user_id=USER,
        user_id=USER,
        reservation_id=reservation["reservation_id"],
        captured_credits=2,
        provider_spent_micros=60_000,
    )
    account = ledger.get_account(USER)
    assert captured["captured_credits"] == 2
    assert repeated["idempotent"] is True
    assert account["available_credits"] == 8
    assert account["reserved_credits"] == 0
    assert account["lifetime_captured"] == 2
    assert [event["event_type"] for event in ledger.ledger_events(USER)] == [
        "grant",
        "reserve",
        "capture",
        "release",
    ]
    events = ledger.ledger_events(USER)
    assert sum(event["delta_available"] for event in events) == account["available_credits"]
    assert sum(event["delta_reserved"] for event in events) == account["reserved_credits"]
    assert sum(event["delta_consumed"] for event in events) == account["lifetime_captured"]


def test_financial_events_are_append_only_in_local_reference(tmp_path):
    path = tmp_path / "immutable-credit-ledger.sqlite3"
    ledger = SQLiteCreditLedger(path)
    _grant(ledger)
    with sqlite3.connect(path) as connection:
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            connection.execute("UPDATE credit_ledger_events SET event_type = 'tampered'")
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            connection.execute("DELETE FROM credit_ledger_events")
    assert [event["event_type"] for event in ledger.ledger_events(USER)] == ["grant"]


def test_network_interruption_stays_uncertain_across_restart(tmp_path):
    path = tmp_path / "restart-credit-ledger.sqlite3"
    ledger = SQLiteCreditLedger(path)
    _grant(ledger)
    reservation = _reserve(ledger, credits=3)
    _record_and_settle(ledger, reservation["reservation_id"], state="uncertain")
    uncertain = ledger.mark_uncertain(
        authenticated_user_id=USER,
        user_id=USER,
        reservation_id=reservation["reservation_id"],
        uncertain_provider_micros=100_000,
    )
    assert uncertain["status"] == "uncertain"

    restarted = SQLiteCreditLedger(path)
    repeated = _reserve(restarted, key="request-1", request_hash="hash-1", credits=3)
    assert repeated["reservation_id"] == reservation["reservation_id"]
    assert repeated["status"] == "uncertain"
    with pytest.raises(InvalidLedgerState):
        restarted.release(
            authenticated_user_id=USER,
            user_id=USER,
            reservation_id=reservation["reservation_id"],
        )
    with pytest.raises(InvalidLedgerState):
        restarted.capture(
            authenticated_user_id=USER,
            user_id=USER,
            reservation_id=reservation["reservation_id"],
            captured_credits=0,
            provider_spent_micros=0,
        )
    account = restarted.get_account(USER)
    assert account["available_credits"] == 7
    assert account["reserved_credits"] == 3

    reconciled = restarted.settle_provider_attempt(
        authenticated_user_id=USER,
        user_id=USER,
        reservation_id=reservation["reservation_id"],
        attempt_no=1,
        state="failed",
        actual_cost_micros=0,
        input_tokens=0,
        output_tokens=0,
    )
    assert reconciled["state"] == "failed"
    final = restarted.capture(
        authenticated_user_id=USER,
        user_id=USER,
        reservation_id=reservation["reservation_id"],
        captured_credits=0,
        provider_spent_micros=0,
    )
    assert final["status"] == "captured"
    assert restarted.get_account(USER)["available_credits"] == 10
    assert restarted.get_account(USER)["reserved_credits"] == 0


def test_provider_budget_is_reserved_before_each_attempt(ledger):
    _grant(ledger)
    reservation = _reserve(ledger, credits=2)
    ledger.record_provider_attempt(
        authenticated_user_id=USER,
        user_id=USER,
        reservation_id=reservation["reservation_id"],
        attempt_no=1,
        provider="fixture-provider",
        model="fixture-model-v1",
        max_cost_micros=80_000,
    )
    with pytest.raises(InsufficientCredits):
        ledger.record_provider_attempt(
            authenticated_user_id=USER,
            user_id=USER,
            reservation_id=reservation["reservation_id"],
            attempt_no=2,
            provider="fixture-provider",
            model="fixture-model-v1",
            max_cost_micros=30_000,
        )


def test_capture_requires_a_provider_attempt_and_settled_cost(ledger):
    _grant(ledger)
    reservation = _reserve(ledger, credits=2)
    with pytest.raises(InvalidLedgerState):
        ledger.capture(
            authenticated_user_id=USER,
            user_id=USER,
            reservation_id=reservation["reservation_id"],
            provider_spent_micros=1,
        )


def test_forged_user_id_cannot_mutate_another_account(ledger):
    _grant(ledger)
    before = ledger.ledger_events(USER)
    with pytest.raises(IdentityMismatch):
        ledger.reserve(
            authenticated_user_id="attacker",
            user_id=USER,
            operation_type="test-operation",
            idempotency_key="forged",
            request_hash="forged-hash",
            credits=1,
            provider_budget_micros=50_000,
        )
    assert ledger.get_account(USER)["available_credits"] == 10
    assert ledger.ledger_events(USER) == before


def test_legacy_snapshot_never_overwrites_existing_history(ledger):
    first = ledger.import_legacy_balance(
        authenticated_user_id=USER,
        user_id=USER,
        legacy_credits=300,
        snapshot_key="migration-run-1:user-a",
    )
    repeated = ledger.import_legacy_balance(
        authenticated_user_id=USER,
        user_id=USER,
        legacy_credits=300,
        snapshot_key="migration-run-1:user-a",
    )
    assert first["available_credits"] == 300
    assert repeated["idempotent"] is True
    with pytest.raises(IdempotencyConflict):
        ledger.import_legacy_balance(
            authenticated_user_id=USER,
            user_id=USER,
            legacy_credits=200,
            snapshot_key="migration-run-2:user-a",
        )
    assert ledger.get_account(USER)["available_credits"] == 300
    assert [event["event_type"] for event in ledger.ledger_events(USER)] == [
        "legacy_import"
    ]


def test_expiration_removes_only_available_credits(ledger):
    expiry = datetime.now(timezone.utc) + timedelta(days=1)
    ledger.grant(
        authenticated_user_id=USER,
        user_id=USER,
        credits=7,
        source_type="subscription",
        source_key="period-1",
        expires_at=expiry,
    )
    assert ledger.expire_grants(
        now=expiry + timedelta(seconds=1),
        future_cutoff_approval="test:phase1-expiration",
    ) == 1
    assert ledger.expire_grants(
        now=expiry + timedelta(days=1),
        future_cutoff_approval="test:phase1-repeat",
    ) == 0
    account = ledger.get_account(USER)
    assert account["available_credits"] == 0
    assert account["reserved_credits"] == 0
    assert [event["event_type"] for event in ledger.ledger_events(USER)] == [
        "grant",
        "expire",
    ]


def test_sql_migration_is_non_destructive_and_contains_atomic_contracts():
    migration = _migration_sql()
    for table in (
        "gabriel_credit_accounts",
        "gabriel_credit_grants",
        "gabriel_credit_reservations",
        "gabriel_credit_allocations",
        "gabriel_credit_provider_usage",
        "gabriel_credit_ledger",
    ):
        assert f"create table if not exists public.{table}" in migration
    for operation in (
        "gabriel_credit_grant",
        "gabriel_credit_reserve",
        "gabriel_credit_capture",
        "gabriel_credit_release",
        "gabriel_credit_mark_uncertain",
        "gabriel_credit_expire_grants",
    ):
        assert f"function public.{operation}" in migration
    assert "for update" in migration
    assert "gabriel_credit_ledger_immutable" in migration
    assert "update gabriel_users" not in migration
    assert "alter table gabriel_users" not in migration
    assert "delete from gabriel_users" not in migration


def test_sql_migration_wraps_function_creation_and_permissions_in_one_transaction():
    migration = _migration_sql().strip()
    assert migration.startswith("-- gabriel v3")
    assert re.search(r"(?m)^begin;$", migration)
    assert migration.endswith("commit;")
    assert migration.index("begin;") < migration.index("create table")
    assert migration.rindex("commit;") > migration.rindex("grant execute")


def test_every_created_function_has_public_execute_revoked():
    migration = _migration_sql()
    compact = re.sub(r"\s+", " ", migration)
    signatures = {
        "gabriel_credit_ledger_immutable()": "public, anon, authenticated, service_role",
        "gabriel_credit_assert_actor(text, text)": "public, anon, authenticated, service_role",
        "gabriel_credit_grant(text, text, bigint, text, text, timestamptz, jsonb)": "public, anon, authenticated",
        "gabriel_credit_import_legacy_balance(text, text, bigint, text)": "public, anon, authenticated",
        "gabriel_credit_reserve(text, text, text, text, text, bigint, bigint, text)": "public, anon, authenticated",
        "gabriel_credit_record_provider_attempt(text, text, uuid, integer, text, text, bigint, text)": "public, anon, authenticated",
        "gabriel_credit_settle_provider_attempt(text, text, uuid, integer, text, bigint, bigint, bigint)": "public, anon, authenticated",
        "gabriel_credit_release(text, text, uuid)": "public, anon, authenticated",
        "gabriel_credit_capture(text, text, uuid, bigint, bigint)": "public, anon, authenticated",
        "gabriel_credit_mark_uncertain(text, text, uuid, bigint)": "public, anon, authenticated",
        "gabriel_credit_expire_grants(timestamptz)": "public, anon, authenticated",
    }
    assert set(_function_blocks(migration)) == {
        signature.split("(", 1)[0] for signature in signatures
    }
    for signature, revoked_roles in signatures.items():
        assert (
            f"revoke all on function public.{signature} from {revoked_roles};"
            in compact
        )


def test_only_service_role_can_execute_financial_rpcs():
    migration = _migration_sql()
    grants = re.findall(
        r"grant execute on function public\.([a-z0-9_]+)\([^;]+?\)\s+to\s+([a-z0-9_]+);",
        migration,
        flags=re.DOTALL,
    )
    financial_rpcs = {
        "gabriel_credit_grant",
        "gabriel_credit_import_legacy_balance",
        "gabriel_credit_reserve",
        "gabriel_credit_record_provider_attempt",
        "gabriel_credit_settle_provider_attempt",
        "gabriel_credit_release",
        "gabriel_credit_capture",
        "gabriel_credit_mark_uncertain",
        "gabriel_credit_expire_grants",
    }
    assert {name for name, _role in grants} == financial_rpcs
    assert {role for _name, role in grants} == {"service_role"}
    assert "gabriel_credit_ledger_immutable" not in {name for name, _ in grants}
    assert "gabriel_credit_assert_actor" not in {name for name, _ in grants}
    assert not re.search(
        r"grant execute on function .*\bto\s+(public|anon|authenticated)\b",
        migration,
        flags=re.DOTALL,
    )
def test_security_definer_functions_use_only_trusted_search_path():
    migration = _migration_sql()
    blocks = _function_blocks(migration)
    security_definers = {
        name: block for name, block in blocks.items() if "security definer" in block
    }
    assert len(security_definers) == 9
    for name, block in security_definers.items():
        assert "set search_path = pg_catalog, pg_temp" in block, name
        assert not re.search(r"set search_path\s*=.*\bpublic\b", block), name


def test_application_objects_are_schema_qualified_in_sql_functions():
    migration = _migration_sql()
    application_tables = (
        "gabriel_credit_accounts",
        "gabriel_credit_grants",
        "gabriel_credit_legacy_snapshots",
        "gabriel_credit_reservations",
        "gabriel_credit_allocations",
        "gabriel_credit_provider_usage",
        "gabriel_credit_ledger",
    )
    for table in application_tables:
        assert not re.search(
            rf"\b(from|join|update|into|references|on|alter\s+table)\s+"
            rf"(?!public\.){table}\b",
            migration,
        ), table
        assert not re.search(rf"(?<!public\.)\b{table}%rowtype\b", migration), table
    assert not re.search(
        r"(?<!public\.)\bgabriel_credit_assert_actor\s*\(", migration
    )
    assert "execute function public.gabriel_credit_ledger_immutable()" in migration


def test_migration_does_not_expand_rls_or_table_access():
    migration = _migration_sql()
    assert migration.count("enable row level security") == 7
    assert "disable row level security" not in migration
    assert "create policy" not in migration
    assert not re.search(
        r"grant\s+.+?\s+on\s+(?:table\s+)?public\.gabriel_credit_.+?"
        r"\s+to\s+(public|anon|authenticated)\b",
        migration,
        flags=re.DOTALL,
    )
