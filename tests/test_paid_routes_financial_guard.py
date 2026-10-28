import os
from pathlib import Path

os.environ.setdefault("FLASK_SECRET_KEY", "test-secret-paid-route-guard-only")

import app as app_module


ROOT = Path(__file__).resolve().parents[1]


def test_every_paid_http_route_has_an_explicit_financial_operation():
    app_source = (ROOT / "app.py").read_text(encoding="utf-8")
    expected = {
        "analyze": "psychologue",
        "launch_psychologue_cross_analysis": "psychologue_cross",
        "strategize": "stratege",
        "creator_generate": "createur",
        "creator_refine": "createur_refine",
        "context_chat": "context_chat",
        "voice_transcribe": "voice_stt",
        "voice_speak": "voice_tts",
        "strategy_session_step": "strategy_session",
        "strategy_chat": "strategy_chat",
        "orchestrator_chat": "orchestrator",
    }
    for endpoint, operation in expected.items():
        assert f"'{endpoint}': '{operation}'" in app_source
    assert "operation_type = 'psychologue_preview'" in app_source
    assert "'error_code': 'idempotency_key_required'" in app_source


def test_direct_provider_paths_call_the_common_guard_before_network_io():
    app_source = (ROOT / "app.py").read_text(encoding="utf-8")
    mistral = app_source.split("def _budgeted_mistral_complete", 1)[1].split(
        "# ── RAG", 1
    )[0]
    assert mistral.index("begin_provider_attempt(") < mistral.index("client.chat.complete(")

    openai = app_source.split("def _call_openai_orchestrator", 1)[1].split(
        "def _orchestrator_load_session_state", 1
    )[0]
    assert openai.index("begin_provider_attempt(") < openai.index("requests.post(")

    voice = (ROOT / "agents" / "context_builder" / "voice_provider.py").read_text(
        encoding="utf-8"
    )
    scraper = (ROOT / "services" / "scraper.py").read_text(encoding="utf-8")
    transcribe = voice.split("def transcribe(self, audio_bytes", 2)[2].split(
        "def _synthesize_once", 1
    )[0]
    synthesize = voice.split("def _synthesize_once", 1)[1].split("def synthesize", 1)[0]
    assert transcribe.index("begin_provider_attempt(") < transcribe.index("requests.post(")
    assert synthesize.index("begin_provider_attempt(") < synthesize.index("requests.post(")
    assert scraper.count("_guarded_provider_call(") >= 6
    assert "youtube_data_api" in scraper
    assert "instagram_comments" in scraper
    assert "tiktok_comments" in scraper


def test_async_and_parallel_workers_propagate_the_financial_context():
    app_source = (ROOT / "app.py").read_text(encoding="utf-8")
    analyzer_source = (ROOT / "core" / "analyzer.py").read_text(encoding="utf-8")
    creator_source = (ROOT / "agents" / "createur.py").read_text(encoding="utf-8")
    cross_source = (ROOT / "core" / "cross_pipeline.py").read_text(encoding="utf-8")
    executor_source = (ROOT / "core" / "executor.py").read_text(encoding="utf-8")
    assert app_source.count("target=_financial_background_target(") == 4
    assert "executor.submit(" not in analyzer_source
    assert "pool.submit(" not in creator_source
    assert analyzer_source.count("submit_with_financial_context(") >= 9
    assert creator_source.count("submit_with_financial_context(") >= 2
    assert "executor.submit(" not in cross_source
    assert "submit_with_financial_context(" in cross_source
    assert "pool.map(" not in executor_source
    assert "submit_with_financial_context(" in executor_source


def test_historical_debit_is_bypassed_only_when_both_new_controls_are_enabled():
    app_source = (ROOT / "app.py").read_text(encoding="utf-8")
    helper = app_source.split("def _deduct_legacy_credits", 1)[1].split(
        "def _has_enough_operation_credits", 1
    )[0]
    assert "provider_cost_guard_enabled() and credit_ledger_enabled()" in helper
    assert "_db.deduct_credits" in helper


def test_guard_requires_a_key_with_a_user_facing_428(monkeypatch):
    monkeypatch.setenv("GABRIEL_PROVIDER_COST_GUARD_ENABLED", "true")
    response = app_module.app.test_client().post("/analyze", json={})

    assert response.status_code == 428
    payload = response.get_json()
    assert payload["error_code"] == "idempotency_key_required"
    assert payload["error"] != payload["error_code"]
    assert "Rechargez" in payload["error"]


def test_key_is_optional_while_the_guard_remains_disabled(monkeypatch):
    monkeypatch.setenv("GABRIEL_PROVIDER_COST_GUARD_ENABLED", "false")
    response = app_module.app.test_client().post("/analyze", json={})

    assert response.status_code != 428


def test_replayed_operation_is_reported_safely_without_a_second_provider_call():
    with app_module.app.test_request_context("/strategize"):
        response = app_module._financial_error_response(
            app_module.FinancialReplayBlocked("synthetic replay")
        )

    assert response.status_code == 409
    payload = response.get_json()
    assert payload["error_code"] == "financial_operation_replayed"
    assert "Aucun nouvel appel IA" in payload["error"]


def test_frontend_transport_is_loaded_by_both_application_shells():
    base = (ROOT / "templates" / "base.html").read_text(encoding="utf-8")
    v2 = (ROOT / "templates" / "gabriel_v2.html").read_text(encoding="utf-8")
    transport = (ROOT / "static" / "js" / "gabriel-idempotency.js").read_text(
        encoding="utf-8"
    )

    for template in (base, v2):
        assert "js/gabriel-idempotency.js" in template
        assert "installGabrielIdempotency(window)" in template
    assert "'/voice/transcribe'" in transport
    assert "'/voice/speak'" in transport
    assert "'/api/v2/conversations/messages'" in transport
