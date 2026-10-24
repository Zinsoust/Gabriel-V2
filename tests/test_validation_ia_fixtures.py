"""Contrats locaux des fixtures de validation IA A et B.

Ces tests ne contactent aucun fournisseur : le CSV est importé en mémoire par
la route existante, et l'analyse historique est sauvegardée dans un répertoire
temporaire via l'adaptateur local avant d'être relue par la route applicative.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import os
from collections import Counter
from pathlib import Path

import pytest


os.environ["AUTH_ENABLED"] = "true"
os.environ["RATE_LIMIT_ENABLED"] = "false"
os.environ["SUPABASE_URL"] = ""
os.environ["SUPABASE_KEY"] = ""
os.environ["MISTRAL_API_KEY"] = ""
os.environ["MISTRAL_VALIDATION_BUDGET_ENABLED"] = "false"
os.environ.setdefault("FLASK_SECRET_KEY", "test-only-validation-fixtures")

import api.db as db
import app as app_module
from agents.context_builder.schema import missing_required_fields
from agents.stratege import _build_psycho_context
from services.file_importer import normalize_comment_items, parse_comments_file


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "validation_ia"
CSV_PATH = FIXTURES / "clairbureau_comments_120.csv"
SCENARIO_A_PATH = FIXTURES / "scenario_a_clairbureau.json"
BRIEF_V1_PATH = FIXTURES / "scenario_b_brief_v1.json"
SCENARIO_B_PATH = FIXTURES / "scenario_b_compatibilite.json"
CALLS_PATH = FIXTURES / "call_manifest.json"
MANIFEST_PATH = FIXTURES / "manifest.json"

EXPECTED_THEME_COUNTS = {
    "surcharge_administrative": 32,
    "perte_demande_client": 24,
    "rejet_outils_complexes": 20,
    "objection_prix": 16,
    "visibilite_temps": 14,
    "mefiance_automatisation": 8,
    "positif": 6,
}


def _json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _client(user_id: str):
    client = app_module.app.test_client()
    with client.session_transaction() as session:
        session["user_id"] = user_id
        session["user_email"] = f"{user_id}@invalid.example"
        session["user_name"] = "Compte de validation fictif"
    return client


def test_clairbureau_csv_has_exact_schema_distribution_and_unique_fictional_rows():
    with CSV_PATH.open(encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)

    assert reader.fieldnames == ["comment_id", "theme", "comment", "likes"]
    assert len(rows) == 120
    assert Counter(row["theme"] for row in rows) == Counter(EXPECTED_THEME_COUNTS)
    assert len({row["comment_id"] for row in rows}) == 120
    assert len({row["comment"].casefold() for row in rows}) == 120
    assert all(row["comment_id"] == f"CB-{index:03d}" for index, row in enumerate(rows, 1))
    assert all(len(row["comment"].strip()) >= 40 for row in rows)
    assert all(row["likes"].isdigit() for row in rows)

    scenario = _json(SCENARIO_A_PATH)
    assert scenario["fictional"] is True
    assert "fictif" in scenario["provenance"].casefold()
    assert "témoignage réel" in scenario["provenance"].casefold()


def test_clairbureau_csv_uses_the_real_file_parser_and_normalizer():
    parsed = parse_comments_file(CSV_PATH.name, CSV_PATH.read_bytes())
    normalized = normalize_comment_items(parsed["items"], source_file=CSV_PATH.name)

    assert parsed["file_type"] == "csv"
    assert parsed["selected_column"] == "comment"
    assert len(normalized) == 120
    assert normalized[0]["text"].startswith("Entre les devis")
    assert normalized[-1]["text"].startswith("Une vue claire")
    assert all(row["source"] == "file_upload" for row in normalized)


def test_clairbureau_csv_is_accepted_by_the_existing_authenticated_upload_route():
    response = _client("validation-user-a").post(
        "/upload-comments-file",
        data={"file": (io.BytesIO(CSV_PATH.read_bytes()), CSV_PATH.name)},
        content_type="multipart/form-data",
    )
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["success"] is True
    assert payload["comments_count"] == 120
    assert payload["selected_column"] == "comment"
    assert len(payload["normalized_comments"]) == 120


def test_scenario_a_has_complete_business_interview_and_one_creator_request():
    scenario = _json(SCENARIO_A_PATH)

    assert missing_required_fields(scenario["business_context"]) == []
    assert {answer["dimension"] for answer in scenario["interview_answers"]} == {
        "identity", "vision", "business_model", "resources",
        "constraints", "history", "objective",
    }
    assert scenario["thomas_request"]["content_type"] == "linkedin"
    assert scenario["thomas_request"]["generate_variant"] is False
    assert scenario["thomas_request"]["use_psycho"] is True
    assert scenario["thomas_request"]["use_strategy"] is True
    assert len(scenario["expected_strategy_decisions"]) == 2


def test_brief_v1_fixture_matches_the_supported_legacy_adapter():
    fixture = _json(BRIEF_V1_PATH)
    result = fixture["entry"]["full_result"]
    context = _build_psycho_context(result)

    assert fixture["fictional"] is True
    assert fixture["load_contract"]["public_import_route_available"] is False
    assert fixture["load_contract"]["remote_insertion_authorized"] is False
    assert context["contract"]["source_schema"] == "psychologue.brief.v1"
    assert context["insights_cles"]["synthese_audience"] == result["brief"]["synthese"]
    assert context["insights_cles"]["insight_cle"] == result["brief"]["insight_cle"]
    assert context["insights_cles"]["action_prioritaire"] == result["brief"]["action_prioritaire"]


@pytest.fixture
def isolated_local_history(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "_supabase", None)
    monkeypatch.setattr(db, "_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(db, "_HISTORY_FILE", str(tmp_path / "history.json"))
    monkeypatch.setenv("AUTH_ENABLED", "true")
    return tmp_path


def test_brief_v1_can_be_seeded_locally_then_loaded_by_the_existing_route(
    isolated_local_history,
):
    fixture = _json(BRIEF_V1_PATH)
    entry = fixture["entry"]
    owner = "validation-user-b-owner"

    db.save_analysis(entry, user_id=owner, folder_id=entry["folder_id"])

    owner_response = _client(owner).get(
        f"/history/{entry['analysis_id']}/load"
    )
    foreign_response = _client("validation-user-b-foreign").get(
        f"/history/{entry['analysis_id']}/load"
    )

    assert owner_response.status_code == 200
    assert owner_response.get_json()["full_result"]["brief"] == entry["full_result"]["brief"]
    assert foreign_response.status_code == 404
    assert "OrbiteCalme" not in foreign_response.get_data(as_text=True)
    app_module._psycho_cache.pop(entry["analysis_id"], None)


def test_scenario_b_is_complete_isolated_and_explicitly_disables_creator_sources():
    scenario = _json(SCENARIO_B_PATH)
    folders = list(scenario["folders"].values())
    thomas = scenario["thomas_alone"]

    assert scenario["fictional"] is True
    assert len(folders) == len(set(folders))
    assert missing_required_fields(scenario["ariane_autonomous"]["business_context"]) == []
    assert thomas["use_psycho"] is False
    assert thomas["use_strategy"] is False
    assert thomas["generate_variant"] is False
    assert scenario["mismatch"]["expected_status"] == 409
    assert scenario["mismatch"]["expected_mistral_attempt_delta"] == 0
    assert len(scenario["contamination_checks"]) == 2


def test_call_manifest_has_a_hard_global_bound_and_consistent_arithmetic():
    calls = _json(CALLS_PATH)

    assert calls["sdk_retries_disabled"] is True
    assert calls["other_provider_fallback_allowed"] is False
    assert calls["scenario_a"]["fixed_max_physical_attempts"] == 82
    assert calls["scenario_b"]["fixed_max_physical_attempts"] == 26
    assert calls["fixed_max_physical_attempts"] == 82 + 26
    assert calls["recommended_global_attempt_cap"] == (
        calls["fixed_max_physical_attempts"] + calls["conditional_attempt_allowance"]
    )


def test_manifest_records_current_sha256_and_only_fictional_sources():
    manifest = _json(MANIFEST_PATH)
    listed = {item["path"]: item for item in manifest["files"]}

    assert manifest["fictional_data_only"] is True
    assert manifest["source_user_data_used"] is False
    assert manifest["remote_database_write_required"] is False
    assert manifest["theme_counts"] == EXPECTED_THEME_COUNTS

    for relative in (
        "tests/fixtures/validation_ia/clairbureau_comments_120.csv",
        "tests/fixtures/validation_ia/scenario_a_clairbureau.json",
        "tests/fixtures/validation_ia/scenario_b_brief_v1.json",
        "tests/fixtures/validation_ia/scenario_b_compatibilite.json",
        "tests/fixtures/validation_ia/call_manifest.json",
    ):
        assert listed[relative]["sha256"] == _sha256(ROOT / relative)
