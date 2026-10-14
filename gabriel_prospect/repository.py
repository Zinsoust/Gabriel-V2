"""Supabase repository for Gabriel Prospect.

No Supabase SDK is imported here: the server-created client is injected from
``app.py``. This keeps credentials server-side and makes the repository fully
testable with an in-memory double.
"""

import datetime
import hashlib
import uuid


IMPORTS_TABLE = "gabriel_prospect_imports"
PROSPECTS_TABLE = "gabriel_prospects"
EVENTS_TABLE = "gabriel_prospect_events"
SUPPRESSIONS_TABLE = "gabriel_prospect_suppressions"

PROSPECT_STATUSES = (
    "to_enrich",
    "qualified",
    "contact_ready",
    "contacted",
    "replied",
    "meeting_scheduled",
    "won",
    "lost",
    "do_not_contact",
)


class ProspectRepositoryError(RuntimeError):
    pass


class ProspectStorageUnavailable(ProspectRepositoryError):
    pass


class ProspectNotFound(ProspectRepositoryError):
    pass


class ProspectConflict(ProspectRepositoryError):
    pass


def _now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _identifier_hash(value):
    if not value:
        return None
    return hashlib.sha256(str(value).strip().casefold().encode("utf-8")).hexdigest()


def _fallback_identity_hash(data):
    if data.get("email") or data.get("linkedin_url"):
        return None
    company = data.get("domain") or data.get("company_name")
    if not company:
        return None
    contact = data.get("contact_full_name")
    identity = f"company:{company}|contact:{contact or '<unassigned>'}"
    return _identifier_hash(identity)


def _result_data(result):
    data = getattr(result, "data", None)
    return data if isinstance(data, list) else []


class SupabaseProspectRepository:
    def __init__(self, client):
        self.client = client

    def _require_storage(self):
        if self.client is None:
            raise ProspectStorageUnavailable("Prospect storage is not configured")

    def _execute(self, query):
        self._require_storage()
        try:
            return query.execute()
        except ProspectRepositoryError:
            raise
        except Exception as exc:
            raise ProspectStorageUnavailable("Prospect storage operation failed") from exc

    def _existing_identifiers(self, user_id, prospects):
        emails = {_identifier_hash(item["data"].get("email")) for item in prospects if item["data"].get("email")}
        linkedins = {_identifier_hash(item["data"].get("linkedin_url")) for item in prospects if item["data"].get("linkedin_url")}
        identities = {_fallback_identity_hash(item["data"]) for item in prospects}
        identities.discard(None)
        existing = []
        if emails:
            result = self._execute(
                self.client.table(PROSPECTS_TABLE)
                .select("prospect_id,email_hash,linkedin_hash")
                .eq("user_id", user_id)
                .in_("email_hash", sorted(emails))
            )
            existing.extend(_result_data(result))
        if linkedins:
            result = self._execute(
                self.client.table(PROSPECTS_TABLE)
                .select("prospect_id,email_hash,linkedin_hash")
                .eq("user_id", user_id)
                .in_("linkedin_hash", sorted(linkedins))
            )
            existing.extend(_result_data(result))
        if identities:
            result = self._execute(
                self.client.table(PROSPECTS_TABLE)
                .select("prospect_id,identity_hash")
                .eq("user_id", user_id)
                .in_("identity_hash", sorted(identities))
            )
            existing.extend(_result_data(result))
        identifiers = sorted((emails | linkedins | identities) - {None})
        suppressed = []
        if identifiers:
            result = self._execute(
                self.client.table(SUPPRESSIONS_TABLE)
                .select("identifier_kind,identifier_hash")
                .eq("user_id", user_id)
                .in_("identifier_hash", identifiers)
            )
            suppressed = _result_data(result)
        return {
            "email": {row.get("email_hash"): row.get("prospect_id") for row in existing if row.get("email_hash")},
            "linkedin": {row.get("linkedin_hash"): row.get("prospect_id") for row in existing if row.get("linkedin_hash")},
            "identity": {row.get("identity_hash"): row.get("prospect_id") for row in existing if row.get("identity_hash")},
            "suppressed_email": {
                row.get("identifier_hash") for row in suppressed if row.get("identifier_kind") == "email"
            },
            "suppressed_linkedin": {
                row.get("identifier_hash") for row in suppressed if row.get("identifier_kind") == "linkedin"
            },
            "suppressed_identity": {
                row.get("identifier_hash") for row in suppressed if row.get("identifier_kind") == "identity"
            },
        }

    def save_selected(self, user_id, prepared):
        self._require_storage()
        if not user_id:
            raise ProspectStorageUnavailable("Missing user scope")
        now = _now()
        import_id = str(uuid.uuid4())
        import_meta = prepared["import"]
        prospects = prepared["prospects"]
        existing = self._existing_identifiers(user_id, prospects)

        import_row = {
            "import_id": import_id,
            "user_id": user_id,
            "source_filename": import_meta["filename"],
            "source_sha256": import_meta["sha256"],
            "source_size_bytes": import_meta["size_bytes"],
            "rows_received": import_meta["rows_received"],
            "rows_selected": len(prospects),
            "created_at": now,
        }
        self._execute(self.client.table(IMPORTS_TABLE).insert(import_row))

        rows = []
        saved = []
        duplicates = []
        for prospect in prospects:
            data = prospect["data"]
            email_hash = _identifier_hash(data.get("email"))
            linkedin_hash = _identifier_hash(data.get("linkedin_url"))
            identity_hash = _fallback_identity_hash(data)
            is_suppressed = (
                email_hash in existing["suppressed_email"]
                or linkedin_hash in existing["suppressed_linkedin"]
                or identity_hash in existing["suppressed_identity"]
            )
            existing_id = (
                existing["email"].get(email_hash)
                or existing["linkedin"].get(linkedin_hash)
                or existing["identity"].get(identity_hash)
            )
            if existing_id or is_suppressed:
                duplicates.append({
                    "source_row": prospect["source_row"],
                    "existing_prospect_id": existing_id,
                    "reason": "do_not_contact" if is_suppressed else "existing_contact",
                })
                continue

            prospect_id = str(uuid.uuid4())
            row = {
                "prospect_id": prospect_id,
                "user_id": user_id,
                "import_id": import_id,
                "source_row": prospect["source_row"],
                "status": "qualified" if prospect["eligibility"].get("eligible_for_contact_preparation") is True else "to_enrich",
                "company_name": data.get("company_name"),
                "company_domain": data.get("domain"),
                "contact_name": data.get("contact_full_name"),
                "job_title": data.get("job_title"),
                "agency_type": data.get("agency_type"),
                "email_hash": email_hash,
                "linkedin_hash": linkedin_hash,
                "identity_hash": identity_hash,
                "icp_score": prospect["score"]["total"],
                "data": data,
                "facts": prospect["facts"],
                "sources": prospect["sources"],
                "unknowns": prospect["unknowns"],
                "validation_errors": prospect["validation_errors"],
                "score": prospect["score"],
                "eligibility": prospect["eligibility"],
                "created_at": now,
                "updated_at": now,
            }
            rows.append(row)
            saved.append({"prospect_id": prospect_id, "source_row": prospect["source_row"]})
            if email_hash:
                existing["email"][email_hash] = prospect_id
            if linkedin_hash:
                existing["linkedin"][linkedin_hash] = prospect_id
            if identity_hash:
                existing["identity"][identity_hash] = prospect_id

        if rows:
            try:
                self._execute(self.client.table(PROSPECTS_TABLE).insert(rows))
            except ProspectStorageUnavailable:
                try:
                    self._execute(
                        self.client.table(IMPORTS_TABLE).delete()
                        .eq("import_id", import_id)
                        .eq("user_id", user_id)
                    )
                except ProspectRepositoryError:
                    pass
                raise

        return {
            "import_id": import_id,
            "saved_count": len(saved),
            "duplicate_count": len(duplicates),
            "saved": saved,
            "duplicates": duplicates,
        }

    def list_prospects(self, user_id, status=None, min_score=0, limit=200):
        self._require_storage()
        query = (
            self.client.table(PROSPECTS_TABLE)
            .select("*")
            .eq("user_id", user_id)
            .gte("icp_score", min_score)
        )
        if status:
            query = query.eq("status", status)
        result = self._execute(query.order("updated_at", desc=True).limit(limit))
        return _result_data(result)

    def get_prospect(self, user_id, prospect_id):
        self._require_storage()
        result = self._execute(
            self.client.table(PROSPECTS_TABLE)
            .select("*")
            .eq("prospect_id", prospect_id)
            .eq("user_id", user_id)
            .limit(1)
        )
        rows = _result_data(result)
        if not rows:
            raise ProspectNotFound("Prospect not found")
        events = self._execute(
            self.client.table(EVENTS_TABLE)
            .select("event_id,event_type,from_status,to_status,details,created_at")
            .eq("prospect_id", prospect_id)
            .eq("user_id", user_id)
            .order("created_at", desc=True)
        )
        return {**rows[0], "events": _result_data(events)}

    def update_status(self, user_id, prospect_id, status):
        current = self.get_prospect(user_id, prospect_id)
        if current.get("status") == "do_not_contact" and status != "do_not_contact":
            raise ProspectConflict("do_not_contact is preserved")
        if current.get("eligibility", {}).get("eligible_for_contact_preparation") is not True and status not in (
            "to_enrich", "lost", "do_not_contact",
        ):
            raise ProspectConflict("contact_not_eligible")
        if current.get("status") == status:
            return current
        result = self._execute(
            self.client.table(PROSPECTS_TABLE)
            .update({"status": status, "updated_at": _now()})
            .eq("prospect_id", prospect_id)
            .eq("user_id", user_id)
        )
        rows = _result_data(result)
        if not rows:
            raise ProspectNotFound("Prospect not found")
        return rows[0]

    def delete_prospect(self, user_id, prospect_id):
        result = self._execute(
            self.client.table(PROSPECTS_TABLE)
            .delete()
            .eq("prospect_id", prospect_id)
            .eq("user_id", user_id)
        )
        if not _result_data(result):
            raise ProspectNotFound("Prospect not found")
        return True


_repository = SupabaseProspectRepository(None)


def init_repository(client):
    global _repository
    _repository = SupabaseProspectRepository(client)


def get_repository():
    return _repository
