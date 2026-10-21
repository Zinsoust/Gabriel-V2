"""Global test isolation for mutable RAG runtime state.

The application keeps committed indexes under ``knowledge/_index``.  Tests
must never rebuild or replace those shared artifacts, even when they exercise
the real agent pipelines.
"""

import os
import sys
import tempfile
from pathlib import Path

import pytest


_previous_rag_index_dir = None
_isolated_rag_indexes = None


def pytest_configure(config):
    """Redirect RAG caches before pytest imports any test module."""
    global _previous_rag_index_dir, _isolated_rag_indexes
    _previous_rag_index_dir = os.environ.get("GABRIEL_RAG_INDEX_DIR")
    _isolated_rag_indexes = tempfile.TemporaryDirectory(
        prefix="gabriel-pytest-rag-"
    )
    os.environ["GABRIEL_RAG_INDEX_DIR"] = _isolated_rag_indexes.name


def pytest_unconfigure(config):
    """Restore the caller's environment and remove the isolated cache."""
    if _previous_rag_index_dir is None:
        os.environ.pop("GABRIEL_RAG_INDEX_DIR", None)
    else:
        os.environ["GABRIEL_RAG_INDEX_DIR"] = _previous_rag_index_dir
    if _isolated_rag_indexes is not None:
        _isolated_rag_indexes.cleanup()


@pytest.fixture(scope="session")
def isolated_rag_index_directory():
    return Path(os.environ["GABRIEL_RAG_INDEX_DIR"])


@pytest.fixture(autouse=True)
def clear_rag_runtime_state():
    module = sys.modules.get("core.rag")
    if module is not None:
        module.clear_runtime_cache()
    yield
    module = sys.modules.get("core.rag")
    if module is not None:
        module.clear_runtime_cache()


@pytest.fixture
def deterministic_vader(monkeypatch):
    """Provide an offline sentiment analyzer to tests exercising the pipeline.

    Production dependency checks remain untouched: only tests that explicitly
    request this fixture receive the deterministic implementation.
    """
    import core.analyzer as analyzer

    class _DeterministicVader:
        _positive = ("merci", "excellent", "debloque", "d\u00e9bloqu\u00e9", "abonne")
        _negative = ("pas convaincu", "freine", "trop cher", "probl\u00e8me")

        def polarity_scores(self, text):
            lowered = str(text).lower()
            positive = sum(marker in lowered for marker in self._positive)
            negative = sum(marker in lowered for marker in self._negative)
            compound = max(-1.0, min(1.0, (positive - negative) * 0.5))
            return {
                "neg": max(0.0, -compound),
                "neu": max(0.0, 1.0 - abs(compound)),
                "pos": max(0.0, compound),
                "compound": compound,
            }

    fake = _DeterministicVader()
    monkeypatch.setattr(analyzer, "_vader_singleton", fake)
    monkeypatch.setattr(analyzer, "_vader_init_error", None)
    return fake
