"""Explicit dependency behavior for the deterministic Psychologue analyzer."""

from pathlib import Path

import pytest

from core import analyzer


def test_vader_is_declared_in_runtime_requirements():
    requirements = (
        Path(__file__).resolve().parents[1] / "requirements.txt"
    ).read_text(encoding="utf-8")
    assert "vaderSentiment>=3.3.2" in requirements


def test_missing_vader_fails_early_with_actionable_diagnostic(monkeypatch):
    missing = ModuleNotFoundError("simulated missing vaderSentiment")
    monkeypatch.setattr(analyzer, "_vader_singleton", None)
    monkeypatch.setattr(analyzer, "_vader_init_error", missing)

    status = analyzer.analyzer_dependency_status()
    assert status["vader"] == {
        "required": True,
        "available": False,
        "error_type": "ModuleNotFoundError",
    }

    with pytest.raises(
        analyzer.AnalyzerDependencyError,
        match=r"vaderSentiment>=3\.3\.2",
    ):
        analyzer.score_comments_math(
            [{"text": "Un commentaire fictif et suffisamment explicite.", "likes": 0}],
            {"relevance_scores": [0.5]},
            title="Test fictif",
        )


def test_available_vader_keeps_deterministic_analysis_operational(monkeypatch):
    class FakeVader:
        def polarity_scores(self, _text):
            return {"compound": 0.5}

    monkeypatch.setattr(analyzer, "_vader_singleton", FakeVader())
    monkeypatch.setattr(analyzer, "_vader_init_error", None)

    result = analyzer.score_comments_math(
        [{"text": "Ce résultat fictif est clair et très utile.", "likes": 0}],
        {"relevance_scores": [0.8]},
        title="Résultat utile",
    )

    assert analyzer.analyzer_dependency_status()["vader"]["available"] is True
    assert result[0]["sentiment"] == "positive"
    assert result[0]["is_spam"] is False
