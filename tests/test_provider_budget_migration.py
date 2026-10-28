from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
SQL_PATH = ROOT / "supabase" / "20261028_provider_budget_guard.sql"


def _sql():
    return SQL_PATH.read_text(encoding="utf-8")


def test_budget_migration_is_additive_transactional_and_has_no_destructive_sql():
    sql = _sql()
    assert re.search(r"^BEGIN;", sql, re.MULTILINE)
    assert re.search(r"^COMMIT;", sql, re.MULTILINE)
    assert "DROP TABLE" not in sql.upper()
    assert "TRUNCATE" not in sql.upper()
    assert "DELETE FROM" not in sql.upper()
    assert not re.search(
        r"(?:INSERT\s+INTO|UPDATE|DELETE\s+FROM)\s+public\.gabriel_credit_ledger\b",
        sql,
        re.IGNORECASE,
    )


def test_budget_tables_are_rls_protected_and_not_publicly_writable():
    sql = _sql()
    for table in (
        "gabriel_provider_budget_periods",
        "gabriel_provider_budget_attempts",
    ):
        assert f"ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY" in sql
        assert f"REVOKE ALL ON TABLE public.{table} FROM PUBLIC, anon, authenticated, service_role" in sql
    assert "CREATE POLICY" not in sql.upper()
    assert not re.search(r"GRANT\s+(?:SELECT|INSERT|UPDATE|DELETE).*?ON TABLE", sql, re.IGNORECASE)


def test_sensitive_rpcs_are_service_role_only_with_safe_search_path():
    sql = _sql()
    sensitive = (
        "gabriel_provider_budget_reserve_attempt",
        "gabriel_provider_budget_settle_attempt",
    )
    assert sql.count("SECURITY DEFINER") == 3
    assert sql.count("SET search_path = pg_catalog, pg_temp") == 3
    for function in sensitive:
        assert f"REVOKE ALL ON FUNCTION public.{function}" in sql
        assert re.search(
            rf"GRANT EXECUTE ON FUNCTION public\.{function}\([\s\S]*?\) TO service_role;",
            sql,
        )


def test_budget_reservation_and_ledger_attempt_share_one_transaction():
    sql = _sql()
    reserve_body = sql.split(
        "CREATE OR REPLACE FUNCTION public.gabriel_provider_budget_reserve_attempt", 1
    )[1].split(
        "CREATE OR REPLACE FUNCTION public.gabriel_provider_budget_settle_attempt", 1
    )[0]
    assert "gabriel_credit_record_provider_attempt" in reserve_body
    assert reserve_body.index("gabriel_credit_record_provider_attempt") < reserve_body.index(
        "global provider budget exceeded"
    )
    assert "gabriel_provider_budget_lock_period" in reserve_body
    helper_body = sql.split(
        "CREATE OR REPLACE FUNCTION public.gabriel_provider_budget_lock_period", 1
    )[1].split(
        "CREATE OR REPLACE FUNCTION public.gabriel_provider_budget_reserve_attempt", 1
    )[0]
    assert "FOR UPDATE" in helper_body
    assert "ON CONFLICT" in helper_body


def test_settlement_preserves_uncertain_cost_and_is_idempotent():
    sql = _sql()
    settle_body = sql.split(
        "CREATE OR REPLACE FUNCTION public.gabriel_provider_budget_settle_attempt", 1
    )[1]
    assert "uncertain_micros = uncertain_micros + v_attempt.max_cost_micros" in settle_body
    assert "provider budget settlement idempotency conflict" in settle_body
    assert "gabriel_credit_settle_provider_attempt" in settle_body
    assert "v_reconcile_uncertain" in settle_body
    assert "uncertain_micros = uncertain_micros - v_attempt.max_cost_micros" in settle_body
