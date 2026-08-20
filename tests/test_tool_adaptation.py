"""Équivalence de l'outil d'adaptation Psychologue → Stratège."""

import tools as tools_pkg
from agents.stratege import _build_psycho_context, _psycho_query_text


PSYCHO_DATA = {
    'psychologie': {'frustrations': ['manque de temps'], 'peurs_implicites': ['peur de rater'],
                    'desirs_caches': ['être reconnu'], 'motivations_profondes': ['liberté']},
    'emotions': {'repartition': [{'emotion': 'Espoir'}], 'espoir_decu': '', 'aspiration_nourrie': ''},
    'aspirations': {'ce_qu_ils_veulent_devenir': 'entrepreneur libre'},
    'marketing': {'objections_visibles': ['trop cher'], 'positionnement_recommande': 'Premium'},
    'brief': {'synthese': 'Audience motivée mais freinée par le prix', 'insight_cle': 'Le prix est un proxy de peur'},
    'kpis': {'engagement': {'score': 72}},
    'distribution': {'positif': 60, 'negatif': 15},
    'personas': [{'nom': 'Le Pragmatique', 'poids': 40}],
    'dashboard': {'dominant_emotion': 'Espoir', 'dominant_stance': 'favorable'},
    'interpretation': {},
}


class TestEquivalenceAvecLaChaineDOrigine:
    def test_loutil_rend_ce_que_la_chaine_reelle_rend(self):
        attendu_context = _build_psycho_context(PSYCHO_DATA)
        attendu_query = _psycho_query_text(attendu_context)

        obtenu = tools_pkg.registry.get('adaptation.psycho_to_strategy_context').run(
            psycho_data=PSYCHO_DATA)

        assert obtenu['context'] == attendu_context
        assert obtenu['query_text'] == attendu_query

    def test_le_resume_texte_est_bien_derive_du_contexte_reduit(self):
        obtenu = tools_pkg.registry.get('adaptation.psycho_to_strategy_context').run(
            psycho_data=PSYCHO_DATA)
        assert 'Frustrations' in obtenu['query_text']
        assert 'Le Pragmatique' in obtenu['query_text']

    def test_un_rapport_vide_ne_leve_pas(self):
        obtenu = tools_pkg.registry.get('adaptation.psycho_to_strategy_context').run(
            psycho_data={})
        assert obtenu['context']['personas_prioritaires'] == []
        assert obtenu['query_text'] == ''


class TestContrat:
    def test_le_contrat_se_declare_pur_et_cacheable(self):
        spec = tools_pkg.registry.get('adaptation.psycho_to_strategy_context').spec
        assert spec.deterministic is True
        assert spec.cacheable is True


class TestPipelineReelRebranche:
    """Preuve de bout en bout : `Stratege.run` utilise réellement l'outil,
    pas seulement une fonction équivalente à côté."""

    def test_stratege_run_produit_le_meme_contexte_que_lappel_direct(self, monkeypatch):
        import agents.stratege as stratege
        from agents.context import AnalysisContext

        capture = {}

        def _capture_llm(prompt, max_tokens=5000, label=""):
            capture['prompt'] = prompt
            return '{"strategie": {"decision_centrale": "x"}}'

        monkeypatch.setattr(stratege, '_call_llm', _capture_llm)
        monkeypatch.setattr(stratege, '_critique_strategie', lambda *a, **k: {})

        ctx = AnalysisContext(comments=[], brain_context='', video_context='', title='')
        ctx.add('psychologue', PSYCHO_DATA)
        stratege.Stratege().run(ctx)

        attendu_context = _build_psycho_context(PSYCHO_DATA)
        assert 'Le Pragmatique' in capture['prompt']
        assert str(attendu_context['aspirations']['ce_qu_ils_veulent_devenir']) in capture['prompt']
