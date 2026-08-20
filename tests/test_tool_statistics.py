"""Équivalence de l'outil des livrables statistiques.

Le fixture n'est pas inventé : `layer1` et `nlp_data` proviennent des vrais
outils déjà déclarés (`audience.score_comments`, `nlp.run_pipeline`) — la
composition réelle du pipeline du Psychologue, pas une forme approximée.
"""

import numpy as np
import pytest

import core.nlp_engine as nlp_engine
import tools as tools_pkg


COMMENTS = [
    {"text": "Ce programme m'a vraiment aidé à structurer mon offre.", "likes": 40},
    {"text": "Le prix reste un frein, mais je comprends la valeur.", "likes": 12},
    {"text": "Pas convaincu par la méthode, trop générique.", "likes": 5},
    {"text": "Excellent accompagnement, résultats concrets rapidement.", "likes": 28},
    {"text": "Le support client est lent à répondre, dommage.", "likes": 7},
    {"text": "Franchement le meilleur investissement de l'année.", "likes": 33},
]


@pytest.fixture
def layer_et_nlp(monkeypatch):
    def _vectorize_fixe(texts):
        base = np.arange(len(texts) * 8, dtype='float32').reshape(len(texts), 8)
        return base / (np.linalg.norm(base, axis=1, keepdims=True) + 1e-9)
    monkeypatch.setattr(nlp_engine, '_vectorize', _vectorize_fixe)

    layer1 = tools_pkg.registry.get('audience.score_comments').run(
        comments=COMMENTS, nlp_data=None, title='Structurer une offre')
    nlp_data = tools_pkg.registry.get('nlp.run_pipeline').run(
        comments=COMMENTS, title='Structurer une offre')
    return layer1, nlp_data


class TestEquivalenceAvecLaFonctionDOrigine:
    def test_loutil_rend_ce_que_compute_pure_statistical_deliverables_rend(self, layer_et_nlp):
        layer1, nlp_data = layer_et_nlp
        from core.nlp_engine import compute_pure_statistical_deliverables

        attendu = compute_pure_statistical_deliverables(layer1, nlp_data, COMMENTS)
        obtenu = tools_pkg.registry.get('statistics.compute_deliverables').run(
            layer1=layer1, nlp_data=nlp_data, comments=COMMENTS)

        assert obtenu == attendu

    def test_les_six_livrables_sont_bien_presents(self, layer_et_nlp):
        layer1, nlp_data = layer_et_nlp
        obtenu = tools_pkg.registry.get('statistics.compute_deliverables').run(
            layer1=layer1, nlp_data=nlp_data, comments=COMMENTS)
        assert set(obtenu) == {
            'positionnement_audience', 'carte_emotionnelle', 'repartition_camps',
            'signaux_lexicaux_dominants', 'clusters_comportementaux',
            'distribution_relevance',
        }


class TestCasLimites:
    def test_layer1_vide_rend_un_dict_vide(self):
        obtenu = tools_pkg.registry.get('statistics.compute_deliverables').run(
            layer1=[], nlp_data={}, comments=[])
        assert obtenu == {}


class TestContrat:
    def test_le_contrat_se_declare_pur_et_cacheable(self):
        spec = tools_pkg.registry.get('statistics.compute_deliverables').spec
        assert spec.deterministic is True
        assert spec.cacheable is True
        assert spec.timeout_s is None
