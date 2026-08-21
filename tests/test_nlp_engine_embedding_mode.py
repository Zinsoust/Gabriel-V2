"""core/nlp_engine.py — le mode embeddings réellement utilisé (sémantique ou
repli TF-IDF) n'était visible qu'en log console, jamais dans la sortie de
run_nlp_pipeline — impossible de savoir a posteriori quel mode a tourné pour
une analyse donnée sans aller lire les logs serveur au moment exact du run.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import numpy as np

import core.nlp_engine as nlp_engine

COMMENTS = [
    {"text": "Ce produit est vraiment excellent, je recommande."},
    {"text": "Franchement déçu par la qualité proposée."},
    {"text": "Un bon rapport qualité prix dans l'ensemble."},
]


def test_embedding_mode_is_semantic_when_the_model_is_available(monkeypatch):
    def fake_vectorize(texts):
        vecs = np.random.rand(len(texts), 8).astype("float32")
        return vecs / np.linalg.norm(vecs, axis=1, keepdims=True)

    monkeypatch.setattr(nlp_engine, '_vectorize', fake_vectorize)

    result = nlp_engine.run_nlp_pipeline(COMMENTS, title="Un sujet de test")

    assert result['embedding_mode'] == 'semantic'
    assert result['embedding_model'] == nlp_engine.EMBEDDING_MODEL_NAME


def test_embedding_mode_is_tfidf_fallback_when_the_model_is_unavailable(monkeypatch):
    monkeypatch.setattr(nlp_engine, '_vectorize', lambda texts: None)

    result = nlp_engine.run_nlp_pipeline(COMMENTS, title="Un sujet de test")

    assert result['embedding_mode'] == 'tfidf_fallback'
    assert result['embedding_model'] is None
