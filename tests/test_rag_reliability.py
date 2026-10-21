"""Reliability contract for RAG caches and semantic availability."""

import pickle

import numpy as np
import pytest

from core import rag


AGENT = "test_rag_reliability"


@pytest.fixture
def isolated_rag(tmp_path, monkeypatch):
    source_dir = tmp_path / "sources"
    source_dir.mkdir()
    (source_dir / "knowledge.md").write_text(
        "Une connaissance déterministe suffisamment longue pour former un "
        "chunk de test et vérifier le comportement du cache sémantique. " * 3,
        encoding="utf-8",
    )
    index_dir = tmp_path / "indexes"
    rag.configure_index_dir(index_dir)
    monkeypatch.setitem(rag._CUSTOM_AGENT_DIRS, AGENT, source_dir)
    rag.clear_runtime_cache()
    yield source_dir, index_dir
    rag.clear_runtime_cache()
    rag.configure_index_dir(None)


def _index_for(source_dir, value=1.0):
    chunks = [{"text": "connaissance fiable", "source": "knowledge", "start": 0}]
    return {
        "chunks": chunks,
        "embeddings": np.asarray([[value, 0.0]]),
        "hash": rag._hash_dir(source_dir),
        "schema_version": 1,
        "mode": "semantic",
    }


def test_valid_cache_is_loaded_without_rebuild(isolated_rag, monkeypatch):
    source_dir, _index_dir = isolated_rag
    path = rag._index_path(AGENT)
    expected = _index_for(source_dir)
    rag._write_cache_atomically(path, expected)
    original = path.read_bytes()

    monkeypatch.setattr(
        rag, "_build_index",
        lambda _agent: pytest.fail("a valid cache must not be rebuilt"),
    )

    loaded = rag._load_or_build(AGENT)

    assert loaded["hash"] == expected["hash"]
    assert path.read_bytes() == original
    assert rag.cache_status(AGENT)["status"] == "valid"


def test_stale_cache_is_detected_and_replaced_atomically(isolated_rag, monkeypatch):
    source_dir, index_dir = isolated_rag
    path = rag._index_path(AGENT)
    stale = _index_for(source_dir)
    stale["hash"] = "outdated"
    rag._write_cache_atomically(path, stale)
    before = path.read_bytes()
    rebuilt = _index_for(source_dir, value=0.5)
    monkeypatch.setattr(rag, "_build_index", lambda _agent: rebuilt)

    loaded = rag._load_or_build(AGENT)

    assert loaded["hash"] == rag._hash_dir(source_dir)
    assert path.read_bytes() != before
    assert rag.cache_status(AGENT)["status"] == "valid"
    assert list(index_dir.glob(f".{path.name}.*.tmp")) == []


def test_corrupt_cache_is_reported_then_rebuilt(isolated_rag, monkeypatch):
    source_dir, _index_dir = isolated_rag
    path = rag._index_path(AGENT)
    path.parent.mkdir(parents=True)
    path.write_bytes(b"not-a-pickle")
    assert rag.cache_status(AGENT)["status"] == "corrupt"
    monkeypatch.setattr(rag, "_build_index", lambda _agent: _index_for(source_dir))

    rag._load_or_build(AGENT)

    assert rag.cache_status(AGENT)["status"] == "valid"


def test_missing_model_never_overwrites_existing_stale_cache(isolated_rag, monkeypatch):
    source_dir, _index_dir = isolated_rag
    path = rag._index_path(AGENT)
    stale = _index_for(source_dir)
    stale["hash"] = "outdated"
    rag._write_cache_atomically(path, stale)
    original = path.read_bytes()
    monkeypatch.setattr(rag, "_get_model", lambda: None)

    with pytest.raises(rag.RAGEmbeddingUnavailableError, match="préservé"):
        rag._load_or_build(AGENT)

    assert path.read_bytes() == original
    assert rag.cache_status(AGENT)["status"] == "stale"


def test_missing_query_model_has_no_fake_semantic_fallback(isolated_rag, monkeypatch):
    source_dir, _index_dir = isolated_rag
    path = rag._index_path(AGENT)
    cached = _index_for(source_dir)
    rag._write_cache_atomically(path, cached)
    original = path.read_bytes()
    rag._indexes[AGENT] = cached
    monkeypatch.setattr(rag, "_get_model", lambda: None)

    with pytest.raises(rag.RAGEmbeddingUnavailableError, match="modèle d'embeddings"):
        rag.search("requête", AGENT)

    assert path.read_bytes() == original


def test_atomic_replace_failure_preserves_previous_cache(isolated_rag, monkeypatch):
    source_dir, index_dir = isolated_rag
    path = rag._index_path(AGENT)
    previous = _index_for(source_dir)
    rag._write_cache_atomically(path, previous)
    original = path.read_bytes()
    replacement = _index_for(source_dir, value=0.25)

    def fail_replace(_source, _destination):
        raise PermissionError("simulated atomic replace failure")

    monkeypatch.setattr(rag.os, "replace", fail_replace)
    with pytest.raises(rag.RAGCacheError, match="atomique"):
        rag._write_cache_atomically(path, replacement)

    assert path.read_bytes() == original
    assert list(index_dir.glob(f".{path.name}.*.tmp")) == []


def test_incomplete_cache_is_explicitly_identified(isolated_rag):
    source_dir, _index_dir = isolated_rag
    path = rag._index_path(AGENT)
    incomplete = _index_for(source_dir)
    incomplete["embeddings"] = None
    path.parent.mkdir(parents=True)
    path.write_bytes(pickle.dumps(incomplete))

    status = rag.cache_status(AGENT)

    assert status["status"] == "incomplete"
    assert status["has_embeddings"] is False


def test_injected_directory_never_targets_repository_cache(isolated_rag):
    _source_dir, index_dir = isolated_rag

    assert rag.get_index_dir() == index_dir.resolve()
    assert rag._index_path(AGENT).parent == index_dir.resolve()
    assert rag.get_index_dir() != rag._DEFAULT_INDEX_DIR
