"""core/llm_client.py — les garde-fous de débit sont partagés par toute l'app.

Avant : une attente sur le sémaphore saturé (plusieurs Cross Analyses
simultanées, par exemple) dégradait silencieusement le temps de réponse — rien
ne la distinguait d'une lenteur du fournisseur LLM lui-même.

Ces garde-fous vivaient auparavant dans ``core/analyzer.py`` et ne protégeaient
donc QUE le Psychologue : le Stratège et le Créateur les contournaient. Ils
sont désormais dans la couche LLM commune. Les tests suivent le mécanisme à son
nouvel emplacement — la garantie testée est inchangée.
"""

import os
import sys
import time
import threading

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import core.analyzer as analyzer
import core.llm_client as llm_client
from core.llm_client import LLMProvider, LLMResponse


class _FakeProvider(LLMProvider):
    name = "fake"

    def complete(self, prompt, *, model, max_tokens, temperature=None, timeout_ms=300_000, system=None):
        return LLMResponse(text="ok", model=model, finish_reason="stop")


def test_a_long_wait_on_the_saturated_queue_is_logged(monkeypatch, capsys):
    monkeypatch.setattr(llm_client, '_semaphore', threading.Semaphore(1))
    monkeypatch.setattr(llm_client, '_MIN_INTERVAL', 0.0)
    monkeypatch.setattr(llm_client, '_default_provider', _FakeProvider())

    llm_client._semaphore.acquire()  # occupe le seul créneau disponible

    def release_after_a_while():
        time.sleep(1.2)
        llm_client._semaphore.release()

    threading.Thread(target=release_after_a_while, daemon=True).start()

    result = analyzer.call_llm("prompt de test", label="test-label")

    captured = capsys.readouterr()
    assert result == 'ok'
    assert '[LLM]' in captured.out
    assert 'attente_file=' in captured.out
    assert 'label=test-label' in captured.out


def test_no_contention_stays_silent(monkeypatch, capsys):
    """Le créneau est libre : pas d'attente, pas de trace de file — le message
    ne doit apparaître que quand il y a réellement contention."""
    monkeypatch.setattr(llm_client, '_semaphore', threading.Semaphore(1))
    monkeypatch.setattr(llm_client, '_MIN_INTERVAL', 0.0)
    monkeypatch.setattr(llm_client, '_default_provider', _FakeProvider())

    analyzer.call_llm("prompt de test", label="test-label")

    captured = capsys.readouterr()
    assert 'attente_file=' not in captured.out


def test_the_legacy_name_still_points_at_the_same_function(monkeypatch):
    """``_call_claude`` mentait sur le fournisseur (il appelle Mistral). L'alias
    reste le temps que les appelants migrent, mais il doit rester strictement
    équivalent — pas une seconde implémentation qui pourrait diverger."""
    assert analyzer._call_claude is analyzer.call_llm
