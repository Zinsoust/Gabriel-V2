"""Équivalence de l'outil anti-hallucination.

Le fixture reproduit la vraie forme de `evidence_index` telle que déclarée
dans `core/cross_analysis.py::build_cross_analysis`, pas une approximation.
"""

import tools as tools_pkg
from core.cross_interpreter import ground_llm_output


CROSS_RESULT = {
    'source_ids': ['src_a', 'src_b'],
    'evidence_index': {
        'emotions_espoir': {
            'category': 'emotions', 'label': 'Espoir',
            'source_signals': [{'source_id': 'src_a'}, {'source_id': 'src_b'}],
        },
    },
}


class TestEquivalenceAvecLaFonctionDOrigine:
    def test_loutil_rend_ce_que_ground_llm_output_rend(self):
        parsed = {
            'executive_summary': {'text': 'Résumé', 'confidence_level': 'moderate'},
            'common_psychological_core': {'source_ids': ['src_a', 'src_inventee']},
            'convergence_interpretations': [
                {'insight_id': 'emotions_espoir', 'interpretation': 'x',
                 'source_ids': ['src_a']},
            ],
        }
        attendu = ground_llm_output(parsed, CROSS_RESULT)
        obtenu = tools_pkg.registry.get('grounding.ground_claims').run(
            parsed=parsed, cross_result=CROSS_RESULT)
        assert obtenu == attendu


class TestRejetDesAffirmationsSansAncrage:
    def test_une_source_inventee_est_retiree(self):
        parsed = {'common_psychological_core': {'source_ids': ['src_a', 'src_fantome']}}
        obtenu = tools_pkg.registry.get('grounding.ground_claims').run(
            parsed=parsed, cross_result=CROSS_RESULT)
        assert obtenu['common_psychological_core']['source_ids'] == ['src_a']

    def test_un_insight_id_invente_est_rejete_et_compte(self):
        parsed = {'convergence_interpretations': [
            {'insight_id': 'insight_qui_nexiste_pas', 'interpretation': 'x',
             'source_ids': ['src_a']},
        ]}
        obtenu = tools_pkg.registry.get('grounding.ground_claims').run(
            parsed=parsed, cross_result=CROSS_RESULT)
        assert obtenu['convergence_interpretations'] == []
        assert obtenu['validation']['convergence_rejected'] == 1

    def test_un_rejet_nest_jamais_un_silence(self):
        """Le compte de rejets doit rester visible même quand tout est
        rejeté — sinon un retrait ressemble à une absence de contenu."""
        parsed = {'convergence_interpretations': [
            {'insight_id': 'invente', 'interpretation': 'x', 'source_ids': ['src_a']},
            {'insight_id': 'aussi_invente', 'interpretation': 'y', 'source_ids': ['src_b']},
        ]}
        obtenu = tools_pkg.registry.get('grounding.ground_claims').run(
            parsed=parsed, cross_result=CROSS_RESULT)
        assert obtenu['convergence_interpretations'] == []
        assert obtenu['validation']['convergence_rejected'] == 2

    def test_une_affirmation_bien_ancree_est_conservee(self):
        parsed = {'convergence_interpretations': [
            {'insight_id': 'emotions_espoir', 'interpretation': 'Espoir partagé',
             'source_ids': ['src_a', 'src_b'], 'confidence_level': 'strong'},
        ]}
        obtenu = tools_pkg.registry.get('grounding.ground_claims').run(
            parsed=parsed, cross_result=CROSS_RESULT)
        assert len(obtenu['convergence_interpretations']) == 1
        assert obtenu['validation']['convergence_rejected'] == 0


class TestContrat:
    def test_le_contrat_se_declare_pur_et_cacheable(self):
        spec = tools_pkg.registry.get('grounding.ground_claims').spec
        assert spec.deterministic is True
        assert spec.cacheable is True
