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
os.environ.setdefault("MISTRAL_API_KEY", "test-key")
os.environ.setdefault("SUPABASE_URL", "")
os.environ.setdefault("SUPABASE_KEY", "")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

import app as app_module


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

    for source_file in package_dir.glob("*.py"):
        tree = ast.parse(source_file.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported_roots.update(alias.name.split(".", 1)[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported_roots.add(node.module.split(".", 1)[0])

    assert imported_roots.isdisjoint(forbidden_roots)
