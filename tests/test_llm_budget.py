"""Strict Mistral validation budget tests; all providers are local fakes."""

import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor

import pytest

import core.llm_client as llm_client
from core.llm_budget import (
    MistralBudgetConfigurationError,
    MistralBudgetExceeded,
    MistralBudgetGuard,
)
from core.llm_client import LLMProvider, LLMResponse, RetryPolicy


MODEL = 'mistral-test-202610'


def _configure(monkeypatch, tmp_path, *, budget='1.00', run_id='test-run',
               input_rate='0.10', output_rate='1.00'):
    ledger = tmp_path / 'mistral-budget.sqlite3'
    monkeypatch.setenv('MISTRAL_VALIDATION_BUDGET_ENABLED', 'true')
    monkeypatch.setenv('MISTRAL_VALIDATION_RUN_ID', run_id)
    monkeypatch.setenv('MISTRAL_VALIDATION_BUDGET_USD', budget)
    monkeypatch.setenv('MISTRAL_VALIDATION_MAX_ATTEMPTS', '100')
    monkeypatch.setenv('MISTRAL_VALIDATION_LEDGER_PATH', str(ledger.resolve()))
    monkeypatch.setenv('MISTRAL_VALIDATION_INPUT_MARGIN', '1.25')
    monkeypatch.setenv('MISTRAL_VALIDATION_PRICING_JSON', json.dumps({MODEL: {
        'input_usd_per_million': input_rate,
        'output_usd_per_million': output_rate,
    }}))
    monkeypatch.setitem(llm_client.MODEL_TIERS, 'deep', MODEL)
    return ledger


class FakeMistral(LLMProvider):
    name = 'mistral'

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
        return LLMResponse(
            text='ok', model=model, prompt_tokens=10,
            completion_tokens=5, finish_reason='stop',
        )


class RateLimitError(RuntimeError):
    status_code = 429


def _attempt_rows(ledger):
    with sqlite3.connect(ledger) as conn:
        return conn.execute(
            'SELECT status, reserved_microusd, actual_microusd '
            'FROM mistral_budget_attempts ORDER BY created_at'
        ).fetchall()


def test_validation_budget_is_disabled_by_default(monkeypatch):
    monkeypatch.delenv('MISTRAL_VALIDATION_BUDGET_ENABLED', raising=False)
    assert MistralBudgetGuard.from_env() is None


@pytest.mark.parametrize('missing', [
    'MISTRAL_VALIDATION_RUN_ID',
    'MISTRAL_VALIDATION_BUDGET_USD',
    'MISTRAL_VALIDATION_MAX_ATTEMPTS',
    'MISTRAL_VALIDATION_LEDGER_PATH',
    'MISTRAL_VALIDATION_PRICING_JSON',
])
def test_enabled_mode_fails_closed_when_configuration_is_missing(monkeypatch, tmp_path, missing):
    _configure(monkeypatch, tmp_path)
    monkeypatch.delenv(missing, raising=False)
    with pytest.raises(MistralBudgetConfigurationError):
        MistralBudgetGuard.from_env()


def test_mobile_model_alias_is_refused_before_call(monkeypatch, tmp_path):
    _configure(monkeypatch, tmp_path)
    monkeypatch.setenv('MISTRAL_VALIDATION_PRICING_JSON', json.dumps({
        'mistral-small-latest': {
            'input_usd_per_million': '0.1',
            'output_usd_per_million': '0.6',
        }
    }))
    with pytest.raises(MistralBudgetConfigurationError, match='non fige'):
        MistralBudgetGuard.from_env()


def test_budget_exhaustion_refuses_before_provider_execution(monkeypatch, tmp_path):
    _configure(monkeypatch, tmp_path, budget='0.000001', output_rate='1')
    fake = FakeMistral()
    with pytest.raises(MistralBudgetExceeded):
        llm_client.complete(
            'prompt', provider=fake, max_tokens=2,
            retry=RetryPolicy(max_attempts=1), throttled=False,
        )
    assert fake.calls == 0


def test_attempt_limit_is_global_and_atomic(monkeypatch, tmp_path):
    _configure(monkeypatch, tmp_path)
    monkeypatch.setenv('MISTRAL_VALIDATION_MAX_ATTEMPTS', '1')
    guard = MistralBudgetGuard.from_env()
    guard.reserve(
        model=MODEL, input_text='x', max_output_tokens=1,
        label='first', attempt_number=1,
    )
    with pytest.raises(MistralBudgetExceeded, match='tentatives'):
        guard.reserve(
            model=MODEL, input_text='x', max_output_tokens=1,
            label='second', attempt_number=2,
        )


def test_each_retry_is_reserved_and_network_failure_stays_uncertain(monkeypatch, tmp_path):
    ledger = _configure(monkeypatch, tmp_path)
    fake = FakeMistral([RateLimitError(), None])
    response = llm_client.complete(
        'prompt', provider=fake, max_tokens=20, label='retry-test',
        retry=RetryPolicy(max_attempts=2, base_delay=0), throttled=False,
    )
    assert response.text == 'ok'
    rows = _attempt_rows(ledger)
    assert fake.calls == 2
    assert len(rows) == 2
    assert rows[0][0].startswith('failed_uncertain_')
    assert rows[0][2] is None
    assert rows[1][0] == 'settled'


def test_reservation_survives_restart_and_blocks_reuse(monkeypatch, tmp_path):
    _configure(
        monkeypatch, tmp_path, budget='0.000051',
        input_rate='0.000001', output_rate='10',
    )
    first = MistralBudgetGuard.from_env()
    first.reserve(
        model=MODEL, input_text='x', max_output_tokens=5,
        label='crash', attempt_number=1,
    )
    restarted = MistralBudgetGuard.from_env()
    assert restarted.accounted_microusd() == 51
    with pytest.raises(MistralBudgetExceeded):
        restarted.reserve(
            model=MODEL, input_text='x', max_output_tokens=5,
            label='after-restart', attempt_number=1,
        )


def test_parallel_reservations_are_atomic(monkeypatch, tmp_path):
    _configure(
        monkeypatch, tmp_path, budget='0.000051', run_id='parallel-run',
        input_rate='0.000001', output_rate='10',
    )
    def reserve_once(number):
        try:
            # Each worker builds its own guard, as independent application
            # entry points do before reaching the shared ledger.
            guard = MistralBudgetGuard.from_env()
            guard.reserve(
                model=MODEL, input_text='x', max_output_tokens=5,
                label='parallel', attempt_number=number,
            )
            return True
        except MistralBudgetExceeded:
            return False

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(reserve_once, range(1, 9)))
    assert results.count(True) == 1
    guard = MistralBudgetGuard.from_env()
    assert guard.accounted_microusd() == 51


def test_network_error_keeps_full_reservation(monkeypatch, tmp_path):
    ledger = _configure(monkeypatch, tmp_path)
    fake = FakeMistral([ConnectionError('offline')])
    with pytest.raises(ConnectionError):
        llm_client.complete(
            'prompt', provider=fake, max_tokens=20,
            retry=RetryPolicy(max_attempts=1), throttled=False,
        )
    row = _attempt_rows(ledger)[0]
    assert row[0].startswith('failed_uncertain_')
    assert row[2] is None
    assert MistralBudgetGuard.from_env().accounted_microusd() == row[1]


def test_fallback_to_another_provider_is_refused(monkeypatch, tmp_path):
    _configure(monkeypatch, tmp_path)

    class OtherProvider(FakeMistral):
        name = 'openai'

    fake = OtherProvider()
    with pytest.raises(MistralBudgetConfigurationError, match='fallback'):
        llm_client.complete('prompt', provider=fake, throttled=False)
    assert fake.calls == 0


def test_missing_usage_keeps_the_conservative_reservation(monkeypatch, tmp_path):
    ledger = _configure(monkeypatch, tmp_path)
    guard = MistralBudgetGuard.from_env()
    reservation = guard.reserve(
        model=MODEL, input_text='prompt', max_output_tokens=10,
        label='unmetered', attempt_number=1,
    )
    guard.settle(
        reservation, response_model=MODEL,
        input_tokens=None, output_tokens=None,
    )
    row = _attempt_rows(ledger)[0]
    assert row[0] == 'failed_uncertain_usage_missing'
    assert row[2] is None
    assert guard.accounted_microusd() == reservation.reserved_microusd


def test_model_fallback_mismatch_is_retained_and_stopped(monkeypatch, tmp_path):
    ledger = _configure(monkeypatch, tmp_path)
    guard = MistralBudgetGuard.from_env()
    reservation = guard.reserve(
        model=MODEL, input_text='prompt', max_output_tokens=10,
        label='model-fallback', attempt_number=1,
    )
    with pytest.raises(MistralBudgetConfigurationError, match='different'):
        guard.settle(
            reservation, response_model='another-versioned-model',
            input_tokens=10, output_tokens=5,
        )
    row = _attempt_rows(ledger)[0]
    assert row[0] == 'failed_uncertain_model_mismatch'
    assert row[2] is None


def test_keyboard_interrupt_is_accounted_as_uncertain(monkeypatch, tmp_path):
    ledger = _configure(monkeypatch, tmp_path)
    fake = FakeMistral([KeyboardInterrupt()])
    with pytest.raises(KeyboardInterrupt):
        llm_client.complete(
            'prompt', provider=fake, max_tokens=20,
            retry=RetryPolicy(max_attempts=1), throttled=False,
        )
    assert _attempt_rows(ledger)[0][0] == 'failed_uncertain_KeyboardInterrupt'


def test_ledger_never_stores_prompt_or_message_content(monkeypatch, tmp_path):
    ledger = _configure(monkeypatch, tmp_path)
    guard = MistralBudgetGuard.from_env()
    guard.reserve(
        model=MODEL, input_text='PRIVATE USER CONTENT', max_output_tokens=10,
        label='privacy', attempt_number=1,
    )
    with sqlite3.connect(ledger) as conn:
        columns = {row[1] for row in conn.execute('PRAGMA table_info(mistral_budget_attempts)')}
        serialized = '\n'.join(
            str(row) for row in conn.execute('SELECT * FROM mistral_budget_attempts')
        )
    assert 'prompt' not in columns and 'messages' not in columns
    assert 'PRIVATE USER CONTENT' not in serialized


def test_same_run_cannot_change_budget_or_prices(monkeypatch, tmp_path):
    _configure(monkeypatch, tmp_path, budget='1.00')
    MistralBudgetGuard.from_env()
    monkeypatch.setenv('MISTRAL_VALIDATION_BUDGET_USD', '2.00')
    with pytest.raises(MistralBudgetConfigurationError, match='existe deja'):
        MistralBudgetGuard.from_env()
