from pathlib import Path


MIGRATION = Path(__file__).parents[2] / "supabase" / "20261012_gabriel_prospect_mvp3.sql"


def test_migration_defines_minimal_tables_and_rls():
    sql = MIGRATION.read_text(encoding="utf-8").lower()

    for table in ("gabriel_prospect_imports", "gabriel_prospects", "gabriel_prospect_events"):
        assert f"create table if not exists {table}" in sql
        assert f"alter table {table} enable row level security" in sql
        assert f"alter table {table} force row level security" in sql
        assert f"auth.uid()::text = user_id" in sql


def test_migration_deduplicates_contacts_but_never_companies_by_domain():
    sql = MIGRATION.read_text(encoding="utf-8").lower()

    assert "email_hash" in sql and "linkedin_hash" in sql
    assert "identity_hash" in sql
    assert "unique" in sql
    assert "unique (user_id, domain" not in sql
    assert "unique (user_id, company_domain" not in sql


def test_migration_preserves_status_history_and_do_not_contact():
    sql = MIGRATION.read_text(encoding="utf-8").lower()

    assert "do_not_contact" in sql
    assert "gabriel_prospect_log_change" in sql
    assert "old.status = 'do_not_contact'" in sql
    assert "on delete cascade" in sql


def test_migration_supports_enrichment_and_persistent_suppression():
    sql = MIGRATION.read_text(encoding="utf-8").lower()

    assert "'to_enrich'" in sql
    assert "gabriel_prospect_contact_status_guard" in sql
    assert "eligible_for_contact_preparation" in sql
    assert "create table if not exists gabriel_prospect_suppressions" in sql
    assert "alter table gabriel_prospect_suppressions enable row level security" in sql
