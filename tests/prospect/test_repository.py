from types import SimpleNamespace

import pytest

from gabriel_prospect.repository import (
    ProspectConflict,
    ProspectNotFound,
    ProspectStorageUnavailable,
    SupabaseProspectRepository,
)


class FakeQuery:
    def __init__(self, database, table):
        self.database = database
        self.table = table
        self.operation = "select"
        self.payload = None
        self.filters = []
        self.in_filters = []
        self.minimums = []
        self.maximum = None

    def select(self, *_args):
        self.operation = "select"
        return self

    def insert(self, payload):
        self.operation = "insert"
        self.payload = payload
        return self

    def update(self, payload):
        self.operation = "update"
        self.payload = payload
        return self

    def delete(self):
        self.operation = "delete"
        return self

    def eq(self, field, value):
        self.filters.append((field, value))
        return self

    def in_(self, field, values):
        self.in_filters.append((field, set(values)))
        return self

    def gte(self, field, value):
        self.minimums.append((field, value))
        return self

    def order(self, *_args, **_kwargs):
        return self

    def limit(self, value):
        self.maximum = value
        return self

    def _matches(self, row):
        return (
            all(row.get(field) == value for field, value in self.filters)
            and all(row.get(field) in values for field, values in self.in_filters)
            and all(row.get(field, 0) >= value for field, value in self.minimums)
        )

    def execute(self):
        self.database.calls.append({
            "table": self.table,
            "operation": self.operation,
            "filters": list(self.filters),
            "in_filters": [(field, set(values)) for field, values in self.in_filters],
        })
        rows = self.database.rows.setdefault(self.table, [])
        if self.operation == "select":
            selected = [dict(row) for row in rows if self._matches(row)]
            return SimpleNamespace(data=selected[:self.maximum] if self.maximum else selected)
        if self.operation == "insert":
            inserted = self.payload if isinstance(self.payload, list) else [self.payload]
            if self.table == "gabriel_prospects":
                suppressions = self.database.rows.setdefault("gabriel_prospect_suppressions", [])
                for row in inserted:
                    identifiers = (
                        ("email", row.get("email_hash")),
                        ("linkedin", row.get("linkedin_hash")),
                        ("identity", row.get("identity_hash")),
                    )
                    if any(
                        value
                        and suppression.get("user_id") == row.get("user_id")
                        and suppression.get("identifier_kind") == kind
                        and suppression.get("identifier_hash") == value
                        for kind, value in identifiers
                        for suppression in suppressions
                    ):
                        raise RuntimeError("contact identifier is suppressed")
            rows.extend(dict(row) for row in inserted)
            return SimpleNamespace(data=[dict(row) for row in inserted])
        matched = [row for row in rows if self._matches(row)]
        if self.operation == "update":
            for row in matched:
                old_status = row.get("status")
                row.update(self.payload)
                if old_status != row.get("status"):
                    self.database.rows.setdefault("gabriel_prospect_events", []).append({
                        "event_id": f"event-{len(self.database.rows.get('gabriel_prospect_events', [])) + 1}",
                        "prospect_id": row["prospect_id"],
                        "user_id": row["user_id"],
                        "event_type": "status_changed",
                        "from_status": old_status,
                        "to_status": row["status"],
                        "created_at": "2026-10-12T12:00:00Z",
                    })
            return SimpleNamespace(data=[dict(row) for row in matched])
        if self.operation == "delete":
            removed = [dict(row) for row in matched]
            if self.table == "gabriel_prospects":
                for row in removed:
                    if row.get("status") != "do_not_contact":
                        continue
                    identifiers = [
                        ("email", row.get("email_hash")),
                        ("linkedin", row.get("linkedin_hash")),
                        ("identity", row.get("identity_hash")),
                    ]
                    identifiers = [(kind, value) for kind, value in identifiers if value]
                    if not identifiers:
                        raise RuntimeError("cannot delete do_not_contact without a stable identifier")
                    suppressions = self.database.rows.setdefault("gabriel_prospect_suppressions", [])
                    for kind, value in identifiers:
                        if not any(
                            item.get("user_id") == row.get("user_id")
                            and item.get("identifier_kind") == kind
                            and item.get("identifier_hash") == value
                            for item in suppressions
                        ):
                            suppressions.append({
                                "user_id": row["user_id"],
                                "identifier_kind": kind,
                                "identifier_hash": value,
                            })
            self.database.rows[self.table] = [row for row in rows if not self._matches(row)]
            return SimpleNamespace(data=removed)
        raise AssertionError(self.operation)


class FakeSupabase:
    def __init__(self):
        self.rows = {}
        self.calls = []

    def table(self, name):
        return FakeQuery(self, name)


def _prepared(email="alice@studio.test", linkedin=None, row=2):
    return {
        "import": {
            "filename": "agences.csv",
            "sha256": "a" * 64,
            "size_bytes": 100,
            "rows_received": 1,
        },
        "prospects": [{
            "source_row": row,
            "data": {
                "company_name": "Studio Nord",
                "domain": "studio.test",
                "agency_type": "Agence branding",
                "contact_full_name": "Alice Martin",
                "job_title": "Fondatrice",
                "email": email,
                "linkedin_url": linkedin,
            },
            "facts": [],
            "sources": [],
            "hypotheses": [],
            "unknowns": [],
            "validation_errors": [],
            "score": {"total": 90, "maximum": 100, "criteria": []},
            "duplicate": None,
            "eligibility": {"eligible_for_contact_preparation": True},
        }],
    }


def test_repository_requires_configured_storage():
    repository = SupabaseProspectRepository(None)
    with pytest.raises(ProspectStorageUnavailable):
        repository.list_prospects("user-a")


def test_save_and_list_are_strictly_scoped_by_user():
    database = FakeSupabase()
    repository = SupabaseProspectRepository(database)

    saved_a = repository.save_selected("user-a", _prepared())
    repository.save_selected("user-b", _prepared())
    listed_a = repository.list_prospects("user-a")

    assert saved_a["saved_count"] == 1
    assert len(listed_a) == 1
    assert listed_a[0]["user_id"] == "user-a"
    prospect_calls = [call for call in database.calls if call["table"] == "gabriel_prospects"]
    assert prospect_calls
    scoped_calls = [call for call in prospect_calls if call["operation"] != "insert"]
    assert all(("user_id", "user-a") in call["filters"] or ("user_id", "user-b") in call["filters"] for call in scoped_calls)
    assert {row["user_id"] for row in database.rows["gabriel_prospects"]} == {"user-a", "user-b"}


def test_duplicate_email_across_imports_is_skipped_for_same_user_only():
    database = FakeSupabase()
    repository = SupabaseProspectRepository(database)

    first = repository.save_selected("user-a", _prepared())
    second = repository.save_selected("user-a", _prepared(row=8))
    other_user = repository.save_selected("user-b", _prepared(row=9))

    assert first["saved_count"] == 1
    assert second["saved_count"] == 0
    assert second["duplicate_count"] == 1
    assert other_user["saved_count"] == 1


def test_same_company_domain_does_not_merge_distinct_contacts():
    database = FakeSupabase()
    repository = SupabaseProspectRepository(database)
    repository.save_selected("user-a", _prepared(email="alice@studio.test"))

    result = repository.save_selected("user-a", _prepared(email="bob@studio.test", row=3))

    assert result["saved_count"] == 1
    assert len(repository.list_prospects("user-a")) == 2


def test_status_history_is_returned_and_do_not_contact_is_irreversible():
    database = FakeSupabase()
    repository = SupabaseProspectRepository(database)
    result = repository.save_selected("user-a", _prepared())
    prospect_id = result["saved"][0]["prospect_id"]

    updated = repository.update_status("user-a", prospect_id, "do_not_contact")
    detail = repository.get_prospect("user-a", prospect_id)

    assert updated["status"] == "do_not_contact"
    assert detail["events"][0]["to_status"] == "do_not_contact"
    with pytest.raises(ProspectConflict):
        repository.update_status("user-a", prospect_id, "contacted")


def test_read_update_and_delete_never_cross_user_boundary():
    database = FakeSupabase()
    repository = SupabaseProspectRepository(database)
    result = repository.save_selected("user-a", _prepared())
    prospect_id = result["saved"][0]["prospect_id"]

    with pytest.raises(ProspectNotFound):
        repository.get_prospect("user-b", prospect_id)
    with pytest.raises(ProspectNotFound):
        repository.update_status("user-b", prospect_id, "contacted")
    with pytest.raises(ProspectNotFound):
        repository.delete_prospect("user-b", prospect_id)
    assert repository.get_prospect("user-a", prospect_id)["prospect_id"] == prospect_id
    assert repository.delete_prospect("user-a", prospect_id) is True


def test_contactless_company_is_to_enrich_and_cannot_advance_to_outreach():
    database = FakeSupabase()
    repository = SupabaseProspectRepository(database)
    prepared = _prepared(email=None)
    prepared["prospects"][0]["eligibility"] = {"eligible_for_contact_preparation": False}

    saved = repository.save_selected("user-a", prepared)
    prospect_id = saved["saved"][0]["prospect_id"]

    assert repository.get_prospect("user-a", prospect_id)["status"] == "to_enrich"
    with pytest.raises(ProspectConflict, match="contact_not_eligible"):
        repository.update_status("user-a", prospect_id, "contacted")
    assert repository.update_status("user-a", prospect_id, "lost")["status"] == "lost"


def test_contactless_company_exact_duplicate_is_skipped_across_imports():
    database = FakeSupabase()
    repository = SupabaseProspectRepository(database)
    prepared = _prepared(email=None)
    prepared["prospects"][0]["eligibility"] = {"eligible_for_contact_preparation": False}

    assert repository.save_selected("user-a", prepared)["saved_count"] == 1
    assert repository.save_selected("user-a", _prepared(email=None, row=8))["duplicate_count"] == 1


def test_deleted_do_not_contact_is_suppressed_on_reimport():
    database = FakeSupabase()
    repository = SupabaseProspectRepository(database)
    first = repository.save_selected("user-a", _prepared())
    prospect_id = first["saved"][0]["prospect_id"]
    repository.update_status("user-a", prospect_id, "do_not_contact")

    assert repository.delete_prospect("user-a", prospect_id) is True
    reimport = repository.save_selected("user-a", _prepared(row=7))

    assert reimport["saved_count"] == 0
    assert reimport["duplicate_count"] == 1
    assert reimport["duplicates"][0]["reason"] == "do_not_contact"
    assert reimport["duplicates"][0]["existing_prospect_id"] is None


def test_direct_database_delete_also_preserves_do_not_contact_suppression():
    database = FakeSupabase()
    repository = SupabaseProspectRepository(database)
    first = repository.save_selected("user-a", _prepared())
    prospect_id = first["saved"][0]["prospect_id"]
    repository.update_status("user-a", prospect_id, "do_not_contact")

    database.table("gabriel_prospects").delete().eq("prospect_id", prospect_id).eq("user_id", "user-a").execute()
    reimport = repository.save_selected("user-a", _prepared(row=9))

    assert reimport["saved_count"] == 0
    assert reimport["duplicates"][0]["reason"] == "do_not_contact"


def test_direct_database_insert_cannot_bypass_suppression():
    database = FakeSupabase()
    repository = SupabaseProspectRepository(database)
    first = repository.save_selected("user-a", _prepared())
    prospect_id = first["saved"][0]["prospect_id"]
    blocked_row = dict(repository.get_prospect("user-a", prospect_id))
    blocked_row.pop("events")
    blocked_row["prospect_id"] = "direct-reimport"
    repository.update_status("user-a", prospect_id, "do_not_contact")
    database.table("gabriel_prospects").delete().eq(
        "prospect_id", prospect_id
    ).eq("user_id", "user-a").execute()

    with pytest.raises(RuntimeError, match="contact identifier is suppressed"):
        database.table("gabriel_prospects").insert(blocked_row).execute()


def test_repository_never_inserts_suppressions_directly():
    database = FakeSupabase()
    repository = SupabaseProspectRepository(database)
    first = repository.save_selected("user-a", _prepared())
    prospect_id = first["saved"][0]["prospect_id"]
    repository.update_status("user-a", prospect_id, "do_not_contact")

    assert repository.delete_prospect("user-a", prospect_id) is True
    assert not any(
        call["table"] == "gabriel_prospect_suppressions"
        and call["operation"] == "insert"
        for call in database.calls
    )
