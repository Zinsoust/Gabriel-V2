"""Équivalence de l'outil du pipeline NLP.

`_vectorize` est neutralisé vers des vecteurs *fixes* (pas aléatoires) : la
preuve d'équivalence appelle la fonction d'origine et l'outil séparément,
donc les deux doivent voir exactement les mêmes vecteurs pour être
comparables — un stub aléatoire romprait la comparaison sans révéler de
vrai défaut.
"""

import numpy as np
import pytest

import core.nlp_engine as nlp_engine
import tools as tools_pkg


COMMENTS = [
    {"text": "Ce produit est vraiment excellent, je recommande vivement."},
    {"text": "Franchement déçu par la qualité proposée, dommage."},
    {"text": "Un bon rapport qualité prix dans l'ensemble, satisfait."},
    {"text": "Le service client a été très réactif et efficace."},
    {"text": "Je ne suis pas convaincu, ça manque de finition."},
    {"text": "Livraison rapide, emballage soigné, rien à redire."},
]


@pytest.fixture
def vectorisation_fixe(monkeypatch):
    """Des vecteurs déterministes, dérivés de l'index du commentaire — reproductibles
    d'un appel à l'autre, contrairement à `np.random`."""
    def _fixe(texts):
        base = np.arange(len(texts) * 8, dtype='float32').reshape(len(texts), 8)
        return base / (np.linalg.norm(base, axis=1, keepdims=True) + 1e-9)
    monkeypatch.setattr(nlp_engine, '_vectorize', _fixe)


class TestEquivalenceAvecLaFonctionDOrigine:
    def test_loutil_rend_ce_que_run_nlp_pipeline_rend(self, vectorisation_fixe):
        attendu = nlp_engine.run_nlp_pipeline(COMMENTS, title="Avis produit")
        obtenu = tools_pkg.registry.get('nlp.run_pipeline').run(
            comments=COMMENTS, title="Avis produit")
        assert obtenu == attendu

    def test_le_mode_embeddings_est_semantique_uniquement_avec_un_titre(self, vectorisation_fixe):
        """`embedding_mode` reflète `compute_relevance_scores`, qui ne
        vectorise que si un titre est fourni — même si le clustering, lui,
        vectorise toujours en interne. Subtilité du code d'origine, reproduite
        telle quelle, pas corrigée au passage."""
        avec_titre = tools_pkg.registry.get('nlp.run_pipeline').run(
            comments=COMMENTS, title="Avis produit")
        sans_titre = tools_pkg.registry.get('nlp.run_pipeline').run(comments=COMMENTS)
        assert avec_titre['embedding_mode'] == 'semantic'
        assert sans_titre['embedding_mode'] == 'tfidf_fallback'

    def test_sans_modele_le_repli_tfidf_traverse_intact(self, monkeypatch):
        monkeypatch.setattr(nlp_engine, '_vectorize', lambda texts: None)
        attendu = nlp_engine.run_nlp_pipeline(COMMENTS, title="Avis produit")
        obtenu = tools_pkg.registry.get('nlp.run_pipeline').run(
            comments=COMMENTS, title="Avis produit")
        assert obtenu == attendu
        assert obtenu['embedding_mode'] == 'tfidf_fallback'


class TestContrat:
    def test_le_contrat_se_declare_pur_pour_un_modele_stable(self):
        spec = tools_pkg.registry.get('nlp.run_pipeline').spec
        assert spec.deterministic is True
        assert spec.cacheable is True
        assert spec.parallel_safe is True
