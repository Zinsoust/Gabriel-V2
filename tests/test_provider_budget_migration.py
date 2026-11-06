from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
SQL_PATH = ROOT / "supabase" / "20261028_provider_budget_guard.sql"


def _sql():
    return SQL_PATH.read_text(encoding="utf-8")


def _function_body(sql: str, name: str, next_name: str | None = None) -> str:
    body = sql.split(f"CREATE OR REPLACE FUNCTION public.{name}", 1)[1]
    if next_name:
        body = body.split(f"CREATE OR REPLACE FUNCTION public.{next_name}", 1)[0]
    return body.split("AS $$", 1)[1].split("$$;", 1)[0]


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


def test_all_budget_tables_are_rls_protected_without_runtime_table_access():
    sql = _sql()
    tables = (
        "gabriel_provider_budget_policies",
        "gabriel_provider_budget_policy_events",
        "gabriel_provider_budget_periods",
        "gabriel_provider_budget_attempts",
    )
    for table in tables:
        assert f"ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY" in sql
        assert re.search(
            rf"REVOKE ALL ON TABLE public\.{table}\s+FROM PUBLIC, anon, authenticated, service_role;",
            sql,
        )
    assert "CREATE POLICY" not in sql.upper()
    assert not re.search(r"GRANT\s+(?:SELECT|INSERT|UPDATE|DELETE).*?ON TABLE", sql, re.IGNORECASE)


def test_runtime_rpc_cannot_choose_period_or_limits():
    sql = _sql()
    reserve = _function_body(
        sql,
        "gabriel_provider_budget_reserve_attempt",
        "gabriel_provider_budget_settle_attempt",
    )
    signature = reserve.split(") RETURNS jsonb", 1)[0]
    for forbidden in (
        "p_period_start",
        "p_period_end",
        "p_period_kind",
        "p_user_limit_micros",
        "p_global_limit_micros",
    ):
        assert forbidden not in signature
    assert "enabled" in reserve
    assert "effective_from <= v_now" in reserve
    assert "effective_until IS NULL OR effective_until > v_now" in reserve
    assert "pg_catalog.clock_timestamp()" in reserve
    assert "date_trunc('day'" in reserve
    assert "date_trunc('month'" in reserve
    assert "AT TIME ZONE 'UTC'" in reserve


def test_policy_provisioning_is_separate_disabled_by_default_and_not_runtime_accessible():
    sql = _sql()
    assert "enabled boolean NOT NULL DEFAULT false" in sql
    admin = "gabriel_provider_budget_admin_set_policy"
    assert f"CREATE OR REPLACE FUNCTION public.{admin}" in sql
    assert re.search(
        rf"REVOKE ALL ON FUNCTION public\.{admin}\([\s\S]*?\) FROM PUBLIC, anon, authenticated, service_role;",
        sql,
    )
    assert not re.search(
        rf"GRANT EXECUTE ON FUNCTION public\.{admin}\([\s\S]*?\) TO (?:service_role|anon|authenticated);",
        sql,
    )
    body = _function_body(sql, admin, "gabriel_provider_budget_lock_period")
    assert "provider budget policy cannot change inside an active period" in body
    assert "gabriel_provider_budget_policy_events" in body
    assert "previous_policy" in body and "resulting_policy" in body
    assert "gabriel_provider_budget_policy_events_immutable" in sql


def test_sensitive_functions_have_safe_search_path_and_explicit_execute_contract():
    sql = _sql()
    functions = (
        "gabriel_provider_budget_admin_set_policy",
        "gabriel_provider_budget_lock_period",
        "gabriel_provider_budget_reserve_attempt",
        "gabriel_provider_budget_settle_attempt",
    )
    assert sql.count("SECURITY DEFINER") == len(functions)
    assert sql.count("SET search_path = pg_catalog, pg_temp") == len(functions)
    for function in functions:
        assert f"REVOKE ALL ON FUNCTION public.{function}" in sql
    for function in (
        "gabriel_provider_budget_reserve_attempt",
        "gabriel_provider_budget_settle_attempt",
    ):
        assert re.search(
            rf"GRANT EXECUTE ON FUNCTION public\.{function}\([\s\S]*?\) TO service_role;",
            sql,
        )
    assert sql.count(") TO service_role;") == 2


def test_budget_reservation_and_ledger_attempt_share_one_transaction_and_lock_order():
    sql = _sql()
    reserve = _function_body(
        sql,
        "gabriel_provider_budget_reserve_attempt",
        "gabriel_provider_budget_settle_attempt",
    )
    assert reserve.index("gabriel_credit_record_provider_attempt") < reserve.index(
        "SELECT * INTO v_policy"
    )
    assert reserve.index("'global', 'global'") < reserve.index("'user', p_user_id")
    assert "FOR SHARE" in reserve
    assert "global provider budget exceeded" in reserve
    assert "user provider budget exceeded" in reserve
    helper = _function_body(
        sql,
        "gabriel_provider_budget_lock_period",
        "gabriel_provider_budget_reserve_attempt",
    )
    assert "FOR UPDATE" in helper
    assert "ON CONFLICT" in helper
    assert "non-canonical provider budget period" in helper


def test_settlement_uses_persisted_budget_rows_and_preserves_uncertain_cost():
    sql = _sql()
    settle = _function_body(sql, "gabriel_provider_budget_settle_attempt")
    assert "gabriel_credit_settle_provider_attempt" in settle
    assert "global_budget_id" in settle and "user_budget_id" in settle
    assert "gabriel_provider_budget_lock_period(" not in settle
    assert "uncertain_micros = uncertain_micros + v_attempt.max_cost_micros" in settle
    assert "uncertain_micros = uncertain_micros - v_attempt.max_cost_micros" in settle
    assert "provider budget settlement idempotency conflict" in settle
    assert "GET DIAGNOSTICS v_updated = ROW_COUNT" in settle
    assert "v_updated <> 2" in settle


def test_policy_and_period_constraints_prevent_alternate_or_overlapping_windows():
    sql = _sql()
    assert "provider text NOT NULL UNIQUE" in sql
    assert "period_kind text NOT NULL CHECK (period_kind IN ('day', 'month'))" in sql
    assert "UNIQUE (provider, scope_type, scope_key, period_start)" in sql
    assert "CHECK (user_limit_micros <= global_limit_micros)" in sql
    assert "CHECK (reserved_micros + settled_micros + uncertain_micros <= limit_micros)" in sql
