"""Équivalence de l'outil de comparaison multi-sources.

`build_cross_analysis` porte déjà ses propres validations strictes (bornes
2-5, source_id unique). L'outil doit les laisser passer intactes — les
avaler derrière un message générique effacerait un diagnostic déjà précis.
"""

import pytest

import tools as tools_pkg
from core.cross_analysis import CrossAnalysisValidationError, build_cross_analysis


def _source(source_id, total_comments, confidence, emotion, weight):
    return {
        'source_id': source_id,
        'comment_stats': {'total_comments': total_comments, 'confidence_score': confidence},
        'emotions': [{'label': emotion, 'weight': weight}],
    }


SOURCES = [
    _source('src_a', 150, 90, 'Espoir', 100),
    _source('src_b', 3, 70, 'Espoir', 2),
]


class TestEquivalenceAvecLaFonctionDOrigine:
    def test_loutil_rend_ce_que_build_cross_analysis_rend(self):
        attendu = build_cross_analysis(SOURCES)
        obtenu = tools_pkg.registry.get('comparison.compare_sources').run(
            source_analyses=SOURCES)
        assert obtenu == attendu

    def test_le_signal_partage_est_bien_present(self):
        obtenu = tools_pkg.registry.get('comparison.compare_sources').run(
            source_analyses=SOURCES)
        assert obtenu['shared_emotions'][0]['label'] == 'Espoir'
        assert obtenu['shared_emotions'][0]['sources_count'] == 2


class TestLesValidationsDOrigineTraversentLoutilIntactes:
    def test_moins_de_deux_sources_leve_le_message_precis(self):
        with pytest.raises(CrossAnalysisValidationError, match='entre 2 et 5'):
            tools_pkg.registry.get('comparison.compare_sources').run(
                source_analyses=[SOURCES[0]])

    def test_plus_de_cinq_sources_leve_le_message_precis(self):
        six = [_source(f'src_{i}', 10, 80, 'Espoir', 5) for i in range(6)]
        with pytest.raises(CrossAnalysisValidationError, match='entre 2 et 5'):
            tools_pkg.registry.get('comparison.compare_sources').run(
                source_analyses=six)

    def test_des_source_id_dupliques_levent_le_message_precis(self):
        dupliques = [_source('même_id', 10, 80, 'Espoir', 5),
                    _source('même_id', 10, 80, 'Espoir', 5)]
        with pytest.raises(CrossAnalysisValidationError, match='source_id unique'):
            tools_pkg.registry.get('comparison.compare_sources').run(
                source_analyses=dupliques)

    def test_une_entree_qui_n_est_pas_une_liste_leve_le_message_precis(self):
        with pytest.raises(CrossAnalysisValidationError, match='liste'):
            tools_pkg.registry.get('comparison.compare_sources').run(
                source_analyses="pas une liste")


class TestContrat:
    def test_le_contrat_se_declare_pur_et_cacheable(self):
        spec = tools_pkg.registry.get('comparison.compare_sources').spec
        assert spec.deterministic is True
        assert spec.cacheable is True
        assert spec.timeout_s is None
