from pathlib import Path


MIGRATION = Path(__file__).parents[2] / "supabase" / "20261012_gabriel_prospect_mvp3.sql"


def test_migration_defines_minimal_tables_and_rls():
    sql = MIGRATION.read_text(encoding="utf-8").lower()

    for table in (
        "gabriel_prospect_imports",
        "gabriel_prospects",
        "gabriel_prospect_events",
        "gabriel_prospect_suppressions",
    ):
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


def test_migration_rejects_null_eligibility_for_contact_statuses():
    sql = MIGRATION.read_text(encoding="utf-8").lower()

    assert "coalesce(" in sql
    assert "eligibility ->> 'eligible_for_contact_preparation'" in sql
    assert "gabriel_prospect_identifier_required" in sql


def test_migration_preserves_opposition_on_direct_delete():
    sql = MIGRATION.read_text(encoding="utf-8").lower()

    assert "gabriel_prospect_preserve_suppression" in sql
    assert "before delete on gabriel_prospects" in sql
    assert "old.status = 'do_not_contact'" in sql
    assert "on conflict (user_id, identifier_kind, identifier_hash) do nothing" in sql
    assert "cannot delete do_not_contact without a stable identifier" in sql


def test_migration_rejects_direct_insert_of_suppressed_identifier():
    sql = MIGRATION.read_text(encoding="utf-8").lower()

    assert "gabriel_prospect_reject_suppressed_insert" in sql
    assert "before insert on gabriel_prospects" in sql
    assert "from public.gabriel_prospect_suppressions as suppression" in sql
    assert "contact identifier is suppressed" in sql
    assert "pg_advisory_xact_lock" in sql
    assert "hashtextextended" in sql
    assert (
        "revoke all on function public.gabriel_prospect_reject_suppressed_insert()"
        in sql
    )


def test_migration_is_transactional_and_uses_explicit_least_privilege_grants():
    sql = MIGRATION.read_text(encoding="utf-8").lower().strip()

    assert sql.startswith("begin;") or "\nbegin;" in sql[:500]
    assert sql.endswith("commit;")
    assert "revoke all on table" in sql
    assert "from public, anon, authenticated" in sql
    assert "grant usage on schema public to service_role" in sql
    assert "grant select, insert, update, delete on table gabriel_prospects to service_role" in sql
    assert "grant select on table gabriel_prospect_events to service_role" in sql
    assert "grant select on table gabriel_prospect_suppressions to service_role" in sql
    assert "grant insert on table gabriel_prospect_suppressions to service_role" not in sql
    assert "grant select, insert on table gabriel_prospect_suppressions to service_role" not in sql
    assert "create policy gabriel_prospect_suppressions_insert_own" not in sql
    assert "revoke all on function public.gabriel_prospect_guard_status()" in sql
