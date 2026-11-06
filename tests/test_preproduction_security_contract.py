import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HARDENING = ROOT / "supabase" / "20261029_preproduction_backend_only_security.sql"
MANIFEST = ROOT / "validation" / "supabase_preproduction" / "migration_manifest.json"
AUDIT = ROOT / "validation" / "supabase_preproduction" / "01_readonly_security_audit.sql"
HTTP_GATE = ROOT / "validation" / "supabase_preproduction" / "02_private_beta_http_isolation.py"


def _sql(path: Path) -> str:
    return path.read_text(encoding="utf-8").lower()


def test_backend_only_hardening_is_additive_and_transactional():
    sql = _sql(HARDENING)
    assert sql.strip().startswith("-- gabriel private beta")
    assert re.search(r"\bbegin\s*;", sql)
    assert sql.rstrip().endswith("commit;")
    for forbidden in ("drop table", "drop database", "truncate ", "delete from", "disable row level security"):
        assert forbidden not in sql
    assert "grant " not in sql


def test_backend_only_hardening_requires_complete_schema_and_roles():
    sql = _sql(HARDENING)
    for role in ("anon", "authenticated", "service_role"):
        assert f"'{role}'" in sql
    for table in (
        "gabriel_users",
        "gabriel_analyses",
        "gabriel_folders",
        "gabriel_credit_ledger",
        "gabriel_provider_budget_attempts",
    ):
        assert f"'{table}'" in sql
    assert "required gabriel tables missing" in sql


def test_backend_only_hardening_revokes_every_browser_surface():
    sql = _sql(HARDENING)
    assert "enable row level security" in sql
    assert "revoke all privileges on table" in sql
    assert "revoke all privileges on sequence" in sql
    assert "revoke all privileges on function" in sql
    assert sql.count("from public, anon, authenticated") == 3


def test_manifest_is_ordered_and_excludes_prospect():
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    order = manifest["migration_order_after_core_schema"]
    assert order[-4:] == [
        "supabase/20261024_credit_ledger_phase1.sql",
        "supabase/20261026_credit_ledger_expiration_fix.sql",
        "supabase/20261028_provider_budget_guard.sql",
        "supabase/20261029_preproduction_backend_only_security.sql",
    ]
    assert all("prospect" not in path for path in order)
    assert len(manifest["required_preexisting_schema"]) == 5
    assert manifest["production_data_allowed"] is False


def test_readonly_audit_has_no_mutating_sql():
    sql = _sql(AUDIT)
    assert "begin transaction read only;" in sql
    assert sql.rstrip().endswith("rollback;")
    for forbidden in ("insert ", "update ", "delete ", "create ", "alter ", "drop ", "truncate "):
        assert forbidden not in sql
    for finding in (
        "missing_tables",
        "rls_disabled",
        "table_privilege_leaks",
        "function_execute_leaks",
        "unsafe_security_definers",
        "budget_admin_execute_leaks",
        "missing_service_runtime_execute",
    ):
        assert f"'{finding}'" in sql


def test_http_gate_is_scoped_to_auth_and_folder_isolation_only():
    source = HTTP_GATE.read_text(encoding="utf-8")
    assert "GABRIEL_PREPRODUCTION_EXPECTED_HOST" in source
    assert "I_ACCEPT_SYNTHETIC_WRITES" in source
    assert "/register" in source
    assert "/api/folders" in source
    assert "PRIVATE_BETA_SECURITY=GO" in source
    for paid_route in ("/analyze", "/strategize", "/creator/generate", "/voice/"):
        assert paid_route not in source


def test_preproduction_template_is_fail_closed_and_prospect_off():
    env = (ROOT / "validation" / "supabase_preproduction" / "preproduction.env.example").read_text(
        encoding="utf-8"
    )
    for key in (
        "GABRIEL_CREDIT_LEDGER_ENABLED=false",
        "GABRIEL_PROVIDER_COST_GUARD_ENABLED=false",
        "GABRIEL_PAID_AI_ENABLED=false",
        "GABRIEL_PROSPECT_ENABLED=false",
        "MEMORY_SHARE_ACROSS_USERS=false",
    ):
        assert key in env
    assert "VITE_SUPABASE" not in env and "NEXT_PUBLIC_SUPABASE" not in env


def test_service_role_secret_is_not_referenced_by_browser_sources():
    roots = [ROOT / "frontend-react" / "src", ROOT / "static", ROOT / "templates"]
    leaks = []
    for root in roots:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if path.is_file() and path.suffix.lower() in {".js", ".jsx", ".ts", ".tsx", ".html"}:
                if "SUPABASE_SERVICE_ROLE_KEY" in path.read_text(encoding="utf-8", errors="ignore"):
                    leaks.append(str(path.relative_to(ROOT)))
    assert leaks == []
