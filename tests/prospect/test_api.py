import io
import json
import os
import sys
import ast
from pathlib import Path

import pytest

os.environ["AUTH_ENABLED"] = "true"
os.environ["FLASK_SECRET_KEY"] = "test-secret-prospect-preview"
os.environ["RATE_LIMIT_ENABLED"] = "false"
os.environ["NLP_PRELOAD"] = "false"
os.environ["GABRIEL_PROSPECT_ENABLED"] = "true"
os.environ.setdefault("MISTRAL_API_KEY", "test-key")
os.environ.setdefault("SUPABASE_URL", "")
os.environ.setdefault("SUPABASE_KEY", "")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

import app as app_module
from gabriel_prospect.repository import ProspectConflict, ProspectStorageUnavailable
from gabriel_prospect.provenance import sign_preview
from gabriel_prospect.service import build_import_preview


UID = "test-prospect-user"


def _client(authenticated=True):
    client = app_module.app.test_client()
    if authenticated:
        with client.session_transaction() as session:
            session["user_id"] = UID
            session["user_email"] = "prospect@example.test"
    return client


def _post(client, content=b"Entreprise\nStudio Nord\n", **extra):
    data = {"file": (io.BytesIO(content), "agences.csv"), **extra}
    return client.post(
        "/api/v2/prospects/imports/preview",
        data=data,
        content_type="multipart/form-data",
    )


def test_endpoint_requires_authentication():
    response = _post(_client(authenticated=False))
    assert response.status_code == 401
    assert response.get_json()["error_code"] == "auth_required"


def test_endpoint_returns_preview_without_persisting_anything(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("External persistence or paid service was called")

    monkeypatch.setattr(app_module._db, "get_user_credits", forbidden)
    response = _post(
        _client(),
        (
            "Entreprise,Type agence,Services,Fonction,Effectif,Pays,Email\n"
            "Studio Nord,Agence branding,Identité de marque,Fondatrice,12,France,alice@studio.test\n"
        ).encode("utf-8"),
    )
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["success"] is True
    assert payload["preview"]["summary"]["rows_received"] == 1
    assert payload["preview"]["prospects"][0]["score"]["total"] == 100


def test_endpoint_accepts_explicit_mapping_and_custom_icp_as_json_fields():
    custom_icp = {
        "name": "Belgian micro agencies",
        "version": "test-1",
        "weights": {
            "agency_type": 25,
            "services_fit": 20,
            "decision_maker": 20,
            "employee_count": 15,
            "geography": 10,
            "professional_channel": 10,
        },
        "agency_types": ["studio"],
        "target_services": ["design"],
        "decision_maker_titles": ["owner"],
        "employee_range": {"min": 1, "max": 5},
        "target_geographies": ["Belgique"],
    }
    response = _post(
        _client(),
        b"Org,Kind,Offer,Role,Size,Place,Mail\nAcme,Studio,Design,Owner,3,Belgique,a@acme.test\n",
        mapping=json.dumps(
            {
                "company_name": "Org",
                "agency_type": "Kind",
                "services": "Offer",
                "job_title": "Role",
                "employee_count": "Size",
                "country": "Place",
                "email": "Mail",
            }
        ),
        icp=json.dumps(custom_icp),
    )
    assert response.status_code == 200
    assert response.get_json()["preview"]["prospects"][0]["score"]["total"] == 100


@pytest.mark.parametrize(
    ("data", "error_code", "status_code"),
    [
        ({}, "missing_file", 400),
        ({"file": (io.BytesIO(b"x\n1\n"), "bad.txt")}, "unsupported_file_type", 415),
        ({"file": (io.BytesIO(b"x\n1\n"), "ok.csv"), "mapping": "not-json"}, "invalid_json_field", 400),
    ],
)
def test_endpoint_rejects_invalid_inputs(data, error_code, status_code):
    response = _client().post(
        "/api/v2/prospects/imports/preview",
        data=data,
        content_type="multipart/form-data",
    )
    assert response.status_code == status_code
    assert response.get_json()["error_code"] == error_code


def test_endpoint_rejects_wrong_mime_type():
    response = _client().post(
        "/api/v2/prospects/imports/preview",
        data={"file": (io.BytesIO(b"Entreprise\nAgence\n"), "agences.csv", "image/png")},
        content_type="multipart/form-data",
    )
    assert response.status_code == 415
    assert response.get_json()["error_code"] == "unsupported_media_type"


def test_endpoint_response_does_not_echo_validation_exception_details(monkeypatch):
    from gabriel_prospect import api as prospect_api

    logged = []

    def explode(*args, **kwargs):
        raise RuntimeError("private@example.test should not leak")

    monkeypatch.setattr(prospect_api, "build_import_preview", explode)
    monkeypatch.setattr(prospect_api, "safe_log_event", lambda *args, **kwargs: logged.append((args, kwargs)))
    response = _post(_client())
    assert response.status_code == 500
    assert "private@example.test" not in response.get_data(as_text=True)
    assert response.get_json()["error_code"] == "preview_failed"
    assert "private@example.test" not in repr(logged)
    assert logged[0][1]["metadata"] == {"failure_type": "RuntimeError"}


def test_prospect_package_has_no_external_service_client_imports():
    package_dir = Path(__file__).parents[2] / "gabriel_prospect"
    forbidden_roots = {
        "anthropic", "httpx", "mistralai", "openai", "requests",
        "stripe", "supabase",
    }
    imported_roots = set()
    supabase_importers = set()

    for source_file in package_dir.glob("*.py"):
        tree = ast.parse(source_file.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                roots = {alias.name.split(".", 1)[0] for alias in node.names}
                imported_roots.update(roots)
                if "supabase" in roots:
                    supabase_importers.add(source_file.name)
            elif isinstance(node, ast.ImportFrom) and node.module:
                root = node.module.split(".", 1)[0]
                imported_roots.add(root)
                if root == "supabase":
                    supabase_importers.add(source_file.name)

    assert imported_roots.isdisjoint(forbidden_roots - {"supabase"})
    assert supabase_importers == {"client.py"}


def _save_payload():
    preview = build_import_preview(
        "agences.csv",
        (
            "Entreprise,Type agence,Services,Fonction,Effectif,Pays,Email\n"
            "Studio Nord,Agence branding,Branding,Fondatrice,12,France,alice@studio.test\n"
        ).encode("utf-8"),
    )
    with app_module.app.app_context():
        signed = sign_preview(preview)
    return {"import": signed["import"], "icp": signed["icp"], "prospects": signed["prospects"]}


class _RepositoryStub:
    def __init__(self):
        self.calls = []

    def save_selected(self, user_id, prepared):
        self.calls.append(("save", user_id, prepared))
        return {
            "import_id": "import-1",
            "saved_count": len(prepared["prospects"]),
            "duplicate_count": 0,
            "saved": [{"prospect_id": "prospect-1", "source_row": 2}],
            "duplicates": [],
        }

    def list_prospects(self, user_id, **filters):
        self.calls.append(("list", user_id, filters))
        return [{
            "prospect_id": "prospect-1",
            "user_id": user_id,
            "status": "qualified",
            "data": {"company_name": "Studio Nord"},
            "score": {"total": 90},
        }]

    def get_prospect(self, user_id, prospect_id):
        self.calls.append(("get", user_id, prospect_id))
        return {"prospect_id": prospect_id, "user_id": user_id, "events": []}

    def update_status(self, user_id, prospect_id, status):
        self.calls.append(("status", user_id, prospect_id, status))
        return {"prospect_id": prospect_id, "user_id": user_id, "status": status}

    def delete_prospect(self, user_id, prospect_id):
        self.calls.append(("delete", user_id, prospect_id))
        return True


@pytest.fixture
def repository_stub(monkeypatch):
    from gabriel_prospect import api as prospect_api

    repository = _RepositoryStub()
    monkeypatch.setattr(prospect_api, "get_repository", lambda: repository)
    return repository


@pytest.mark.parametrize(
    ("method", "path", "kwargs"),
    [
        ("get", "/api/v2/prospects", {}),
        ("post", "/api/v2/prospects", {"json": {}}),
        ("get", "/api/v2/prospects/prospect-1", {}),
        ("patch", "/api/v2/prospects/prospect-1/status", {"json": {"status": "contacted"}}),
        ("delete", "/api/v2/prospects/prospect-1", {}),
    ],
)
def test_persistence_routes_require_authentication(method, path, kwargs):
    response = getattr(_client(authenticated=False), method)(path, **kwargs)
    assert response.status_code == 401
    assert response.get_json()["error_code"] == "auth_required"


def test_save_selected_prospects_revalidates_and_passes_authenticated_user(repository_stub):
    response = _client().post("/api/v2/prospects", json=_save_payload())

    assert response.status_code == 201
    assert response.get_json()["result"]["saved_count"] == 1
    operation, user_id, prepared = repository_stub.calls[0]
    assert operation == "save" and user_id == UID
    assert prepared["prospects"][0]["score"]["total"] == 100


def test_save_without_dedicated_storage_returns_controlled_503(monkeypatch):
    from gabriel_prospect import api as prospect_api
    from gabriel_prospect.repository import SupabaseProspectRepository

    monkeypatch.setattr(
        prospect_api,
        "get_repository",
        lambda: SupabaseProspectRepository(None),
    )

    response = _client().post("/api/v2/prospects", json=_save_payload())

    assert response.status_code == 503
    assert response.get_json()["error_code"] == "prospect_storage_unavailable"


def test_save_rejects_tampered_preview_provenance(repository_stub):
    payload = _save_payload()
    payload["prospects"][0]["data"]["company_name"] = "Entreprise substituée"

    response = _client().post("/api/v2/prospects", json=payload)

    assert response.status_code == 400
    assert response.get_json()["error_code"] == "invalid_preview_provenance"
    assert repository_stub.calls == []


def test_list_filters_are_validated_and_scoped(repository_stub):
    response = _client().get("/api/v2/prospects?status=qualified&min_score=70&limit=25")

    assert response.status_code == 200
    assert response.get_json()["prospects"][0]["user_id"] == UID
    assert repository_stub.calls == [("list", UID, {"status": "qualified", "min_score": 70, "limit": 25})]


def test_get_update_and_delete_use_authenticated_user(repository_stub):
    client = _client()
    assert client.get("/api/v2/prospects/prospect-1").status_code == 200
    assert client.patch("/api/v2/prospects/prospect-1/status", json={"status": "contacted"}).status_code == 200
    assert client.delete("/api/v2/prospects/prospect-1").status_code == 200

    assert ("get", UID, "prospect-1") in repository_stub.calls
    assert ("status", UID, "prospect-1", "contacted") in repository_stub.calls
    assert ("delete", UID, "prospect-1") in repository_stub.calls


def test_update_rejects_invalid_status_before_repository_call(repository_stub):
    response = _client().patch(
        "/api/v2/prospects/prospect-1/status",
        json={"status": "reactivated"},
    )

    assert response.status_code == 400
    assert response.get_json()["error_code"] == "invalid_status"
    assert repository_stub.calls == []


def test_do_not_contact_conflict_returns_409(repository_stub, monkeypatch):
    def refuse_reactivation(*_args, **_kwargs):
        raise ProspectConflict("do_not_contact is preserved")

    monkeypatch.setattr(repository_stub, "update_status", refuse_reactivation)
    response = _client().patch(
        "/api/v2/prospects/prospect-1/status",
        json={"status": "contacted"},
    )

    assert response.status_code == 409
    assert response.get_json()["error_code"] == "do_not_contact_preserved"


def test_ineligible_contact_cannot_be_marked_contacted(repository_stub, monkeypatch):
    def refuse_contact(*_args, **_kwargs):
        raise ProspectConflict("contact_not_eligible")

    monkeypatch.setattr(repository_stub, "update_status", refuse_contact)
    response = _client().patch(
        "/api/v2/prospects/prospect-1/status",
        json={"status": "contacted"},
    )

    assert response.status_code == 409
    assert response.get_json()["error_code"] == "contact_not_eligible"


@pytest.mark.parametrize("query", ["status=invalid", "min_score=-1", "min_score=101", "limit=0", "limit=501"])
def test_list_rejects_invalid_filters(repository_stub, query):
    response = _client().get(f"/api/v2/prospects?{query}")
    assert response.status_code == 400
    assert response.get_json()["error_code"] == "invalid_filter"
    assert repository_stub.calls == []


def test_storage_failure_returns_503_without_leaking_details(monkeypatch):
    from gabriel_prospect import api as prospect_api

    class BrokenRepository:
        def list_prospects(self, *_args, **_kwargs):
            raise ProspectStorageUnavailable("secret database host")

    monkeypatch.setattr(prospect_api, "get_repository", lambda: BrokenRepository())
    response = _client().get("/api/v2/prospects")

    assert response.status_code == 503
    assert response.get_json()["error_code"] == "prospect_storage_unavailable"
    assert "secret database host" not in response.get_data(as_text=True)
