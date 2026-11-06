import json
import socket
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

import core.llm_client as llm_client
import services.scraper as scraper
from core.llm_client import LLMProvider, LLMResponse, RetryPolicy
from core.provider_cost_guard import (
    FinancialConfigurationError,
    FinancialLimitExceeded,
    FinancialReplayBlocked,
    FinancialStoreUnavailable,
    UnprotectedProviderCall,
    create_financial_operation,
    load_financial_config,
    reset_financial_backend_for_tests,
    set_financial_backend_for_tests,
    submit_with_financial_context,
)


MODEL = "mistral-versioned-test"


def _configure(monkeypatch, *, operation_budget="1"):
    monkeypatch.setenv("GABRIEL_CREDIT_LEDGER_ENABLED", "true")
    monkeypatch.setenv("GABRIEL_PROVIDER_COST_GUARD_ENABLED", "true")
    monkeypatch.setenv("GABRIEL_PROVIDER_INPUT_TOKEN_MARGIN", "1.25")
    monkeypatch.setenv("GABRIEL_PROVIDER_PRICING_JSON", json.dumps({
        "mistral": {MODEL: {
            "input_usd_per_million": "1.0",
            "output_usd_per_million": "2.0",
        }},
        "openai": {"openai-test": {"max_attempt_usd": "0.0001"}},
        "elevenlabs": {"scribe_v1": {"max_attempt_usd": "0.0001"}},
        "youtube": {"youtube_data_api": {"max_attempt_usd": "0.0001"}},
        "rapidapi": {
            "instagram_comments": {"max_attempt_usd": "0.0001"},
            "tiktok_detail": {"max_attempt_usd": "0.0001"},
            "tiktok_comments": {"max_attempt_usd": "0.0001"},
        },
    }))
    monkeypatch.setenv("GABRIEL_AI_OPERATION_BUDGETS_JSON", json.dumps({
        "psychologue": {
            "credits": 10,
            "provider_budget_usd": operation_budget,
            "pricing_version": "test-v1",
        },
        "context_chat": {
            "credits": 2,
            "provider_budget_usd": operation_budget,
            "pricing_version": "test-v1",
        },
    }))
    monkeypatch.setitem(llm_client.MODEL_TIERS, "deep", MODEL)


class FakeProvider(LLMProvider):
    name = "mistral"

    def __init__(self, outcomes=None):
        self.outcomes = list(outcomes or [])
        self.calls = 0

    def complete(self, prompt, *, model, max_tokens, temperature=None,
                 timeout_ms=300_000, system=None, json_mode=False):
        self.calls += 1
        if self.outcomes:
            outcome = self.outcomes.pop(0)
            if isinstance(outcome, BaseException):
                raise outcome
            if isinstance(outcome, LLMResponse):
                return outcome
        return LLMResponse(
            text="ok", model=model, prompt_tokens=10,
            completion_tokens=5, finish_reason="stop",
        )


class RateLimitError(RuntimeError):
    status_code = 429


class FakeBackend:
    def __init__(self, *, fail_operation=False, fail_attempt=False,
                 fail_settle=False, global_limit=None):
        self.fail_operation = fail_operation
        self.fail_attempt = fail_attempt
        self.fail_settle = fail_settle
        self.global_limit = global_limit
        self.calls = []
        self._lock = threading.Lock()
        self._reservations = {}
        self._attempt_cost = 0

    def reserve_operation(self, **params):
        self.calls.append(("reserve_operation", params))
        if self.fail_operation:
            raise FinancialLimitExceeded("insufficient credits")
        key = (params["p_user_id"], params["p_idempotency_key"])
        with self._lock:
            existed = key in self._reservations
            row = self._reservations.setdefault(key, {
                "reservation_id": f"reservation-{len(self._reservations) + 1}",
                "request_hash": params["p_request_hash"],
            })
            if row["request_hash"] != params["p_request_hash"]:
                raise FinancialLimitExceeded("idempotency conflict")
            result = dict(row)
            result["idempotent"] = existed
            return result

    def reserve_attempt(self, **params):
        self.calls.append(("reserve_attempt", params))
        if self.fail_attempt:
            raise FinancialStoreUnavailable("offline")
        with self._lock:
            cost = params["p_max_cost_micros"]
            if self.global_limit is not None and self._attempt_cost + cost > self.global_limit:
                raise FinancialLimitExceeded("global cap")
            self._attempt_cost += cost
        return {"budget_attempt_id": f"a-{params['p_attempt_no']}"}

    def settle_attempt(self, **params):
        self.calls.append(("settle_attempt", params))
        if self.fail_settle:
            raise FinancialStoreUnavailable("settlement offline")
        return {"state": params["p_state"]}

    def capture(self, **params):
        self.calls.append(("capture", params))
        return {"status": "captured"}

    def release(self, **params):
        self.calls.append(("release", params))
        return {"status": "released"}

    def mark_uncertain(self, **params):
        self.calls.append(("mark_uncertain", params))
        return {"status": "uncertain"}


@pytest.fixture(autouse=True)
def _reset_backend():
    reset_financial_backend_for_tests()
    yield
    reset_financial_backend_for_tests()


def _operation(backend, *, user="user-1", key="request-1", operation="psychologue"):
    set_financial_backend_for_tests(backend)
    return create_financial_operation(
        user_id=user,
        operation_type=operation,
        idempotency_key=key,
        request_hash="hash-1",
    )


def test_guard_is_disabled_by_default(monkeypatch):
    monkeypatch.delenv("GABRIEL_PROVIDER_COST_GUARD_ENABLED", raising=False)
    assert load_financial_config() is None
    fake = FakeProvider()
    assert llm_client.complete("x", provider=fake, throttled=False).text == "ok"


def test_deployed_paid_calls_are_disabled_before_provider_by_default(monkeypatch):
    monkeypatch.setenv("RENDER", "true")
    monkeypatch.delenv("GABRIEL_PAID_AI_ENABLED", raising=False)
    monkeypatch.delenv("GABRIEL_PROVIDER_COST_GUARD_ENABLED", raising=False)
    fake = FakeProvider()
    with pytest.raises(FinancialConfigurationError, match="payants desactives"):
        llm_client.complete("x", provider=fake, throttled=False)
    assert fake.calls == 0


def test_enabled_guard_requires_ledger_and_explicit_prices(monkeypatch):
    monkeypatch.setenv("GABRIEL_PROVIDER_COST_GUARD_ENABLED", "true")
    monkeypatch.setenv("GABRIEL_CREDIT_LEDGER_ENABLED", "false")
    with pytest.raises(FinancialConfigurationError, match="LEDGER_ENABLED"):
        load_financial_config()

    monkeypatch.setenv("GABRIEL_CREDIT_LEDGER_ENABLED", "true")
    with pytest.raises(FinancialConfigurationError, match="PRICING_JSON"):
        load_financial_config()


def test_unprotected_paid_call_is_refused_before_provider(monkeypatch):
    _configure(monkeypatch)
    fake = FakeProvider()
    with pytest.raises(UnprotectedProviderCall):
        llm_client.complete("x", provider=fake, throttled=False)
    assert fake.calls == 0


def test_success_reserves_attempt_settles_and_captures_once(monkeypatch):
    _configure(monkeypatch)
    backend = FakeBackend()
    operation = _operation(backend)
    fake = FakeProvider()

    with operation.bind():
        response = llm_client.complete("prompt", provider=fake, throttled=False)
    operation.finalize_success()
    operation.finalize_success()

    assert response.text == "ok"
    names = [name for name, _ in backend.calls]
    assert names == ["reserve_operation", "reserve_attempt", "settle_attempt", "capture"]
    capture = backend.calls[-1][1]
    assert capture["p_captured_credits"] == 10
    assert capture["p_provider_spent_micros"] > 0

    reserve = next(params for name, params in backend.calls if name == "reserve_attempt")
    assert set(reserve) == {
        "p_authenticated_user_id",
        "p_user_id",
        "p_reservation_id",
        "p_attempt_no",
        "p_provider",
        "p_model",
        "p_max_cost_micros",
        "p_provider_request_id",
    }
    assert not any("limit" in key or "period" in key for key in reserve)


def test_user_without_credits_never_reaches_provider(monkeypatch):
    _configure(monkeypatch)
    backend = FakeBackend(fail_operation=True)
    operation = _operation(backend)
    fake = FakeProvider()
    with operation.bind(), pytest.raises(FinancialLimitExceeded):
        llm_client.complete("prompt", provider=fake, throttled=False)
    operation.finalize_failure()
    assert fake.calls == 0
    assert [name for name, _ in backend.calls] == ["reserve_operation"]


def test_storage_failure_after_credit_reservation_releases_without_provider_call(monkeypatch):
    _configure(monkeypatch)
    backend = FakeBackend(fail_attempt=True)
    operation = _operation(backend)
    fake = FakeProvider()
    with operation.bind(), pytest.raises(FinancialStoreUnavailable):
        llm_client.complete("prompt", provider=fake, throttled=False)
    operation.finalize_failure()
    assert fake.calls == 0
    assert [name for name, _ in backend.calls][-1] == "release"


def test_storage_failure_after_provider_response_never_releases_credits(monkeypatch):
    _configure(monkeypatch)
    backend = FakeBackend(fail_settle=True)
    operation = _operation(backend)
    fake = FakeProvider()
    with operation.bind(), pytest.raises(FinancialStoreUnavailable):
        llm_client.complete("prompt", provider=fake, throttled=False)
    operation.finalize_failure()
    assert fake.calls == 1
    names = [name for name, _ in backend.calls]
    assert "release" not in names and "capture" not in names
    assert names[-1] == "mark_uncertain"


def test_retry_and_fallback_attempts_are_each_reserved(monkeypatch):
    _configure(monkeypatch)
    backend = FakeBackend()
    operation = _operation(backend)
    fake = FakeProvider([RateLimitError(), None])
    with operation.bind():
        result = llm_client.complete(
            "prompt", provider=fake, throttled=False,
            retry=RetryPolicy(max_attempts=2, base_delay=0),
        )
    operation.finalize_success()
    assert result.text == "ok"
    reserves = [params for name, params in backend.calls if name == "reserve_attempt"]
    settlements = [params for name, params in backend.calls if name == "settle_attempt"]
    assert [row["p_attempt_no"] for row in reserves] == [1, 2]
    assert [row["p_state"] for row in settlements] == ["uncertain", "succeeded"]
    assert backend.calls[-1][0] == "mark_uncertain"


def test_paid_collection_retries_are_each_reserved(monkeypatch):
    _configure(monkeypatch)
    monkeypatch.setattr(scraper.time, "sleep", lambda _seconds: None)
    backend = FakeBackend()
    operation = _operation(backend)
    calls = []

    def flaky_collection():
        calls.append(1)
        if len(calls) == 1:
            raise socket.timeout("temporary")
        return {"items": []}

    with operation.bind():
        result = scraper._call_youtube_with_retry(
            flaky_collection, input_text="synthetic-video", max_attempts=2
        )
    operation.finalize_success()

    assert result == {"items": []}
    reserves = [params for name, params in backend.calls if name == "reserve_attempt"]
    settlements = [params for name, params in backend.calls if name == "settle_attempt"]
    assert [row["p_provider"] for row in reserves] == ["youtube", "youtube"]
    assert [row["p_attempt_no"] for row in reserves] == [1, 2]
    assert [row["p_state"] for row in settlements] == ["uncertain", "succeeded"]
    assert backend.calls[-1][0] == "mark_uncertain"


def test_missing_usage_is_charged_at_conservative_ceiling(monkeypatch):
    _configure(monkeypatch)
    backend = FakeBackend()
    operation = _operation(backend)
    fake = FakeProvider([LLMResponse(text="ok", model=MODEL)])
    with operation.bind():
        llm_client.complete("prompt", provider=fake, throttled=False)
    operation.finalize_success()
    reserved = next(p["p_max_cost_micros"] for n, p in backend.calls if n == "reserve_attempt")
    settled = next(p["p_actual_cost_micros"] for n, p in backend.calls if n == "settle_attempt")
    assert settled == reserved


def test_global_cap_is_atomic_under_concurrency(monkeypatch):
    _configure(monkeypatch)
    backend = FakeBackend(global_limit=12)
    set_financial_backend_for_tests(backend)

    def run(number):
        operation = create_financial_operation(
            user_id=f"user-{number}", operation_type="psychologue",
            idempotency_key=f"request-{number}", request_hash=f"hash-{number}",
        )
        fake = FakeProvider([LLMResponse(
            text="ok", model=MODEL, prompt_tokens=1,
            completion_tokens=1, finish_reason="stop",
        )])
        try:
            with operation.bind():
                llm_client.complete("prompt", provider=fake, throttled=False, max_tokens=1)
            operation.finalize_success()
            return True
        except FinancialLimitExceeded:
            operation.finalize_failure()
            return False

    with ThreadPoolExecutor(max_workers=10) as pool:
        results = list(pool.map(run, range(10)))
    assert 0 < results.count(True) < 10
    assert backend._attempt_cost <= 12


def test_financial_context_is_propagated_to_worker_threads(monkeypatch):
    _configure(monkeypatch)
    backend = FakeBackend()
    operation = _operation(backend)
    fake = FakeProvider()
    with operation.bind(), ThreadPoolExecutor(max_workers=1) as pool:
        future = submit_with_financial_context(
            pool, llm_client.complete, "prompt", provider=fake, throttled=False
        )
        assert future.result().text == "ok"
    operation.finalize_success()
    assert fake.calls == 1


def test_same_operation_key_is_idempotent_and_finalization_does_not_double_capture(monkeypatch):
    _configure(monkeypatch)
    backend = FakeBackend()
    operation = _operation(backend, key="stable-key")
    fake = FakeProvider()
    with operation.bind():
        llm_client.complete("prompt", provider=fake, throttled=False)
    operation.finalize_success()
    operation.finalize_success()
    assert [name for name, _ in backend.calls].count("capture") == 1


def test_persistent_request_replay_is_blocked_before_a_second_provider_call(monkeypatch):
    _configure(monkeypatch)
    backend = FakeBackend()
    first = _operation(backend, key="stable-key")
    first_provider = FakeProvider()
    with first.bind():
        llm_client.complete("prompt", provider=first_provider, throttled=False)
    first.finalize_success()

    replay = _operation(backend, key="stable-key")
    replay_provider = FakeProvider()
    with replay.bind(), pytest.raises(FinancialReplayBlocked):
        llm_client.complete("prompt", provider=replay_provider, throttled=False)
    replay.finalize_failure()

    assert first_provider.calls == 1
    assert replay_provider.calls == 0
    assert [name for name, _ in backend.calls].count("capture") == 1
    assert [name for name, _ in backend.calls].count("release") == 0
