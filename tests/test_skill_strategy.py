"""Équivalence du raisonnement stratégique.

Même mécanisme que psychology.human_understanding_grid : un catalogue à une
seule entrée, toujours résolue — pas de variante à choisir.
"""

import pytest

import skills
from agents.stratege import _STRATEGE_SYSTEM


class TestEquivalenceAvecLaConstanteDOrigine:
    @pytest.mark.parametrize('demande', ['stratege', 'autre chose', 'x'])
    def test_toute_demande_non_vide_rend_toujours_le_meme_texte(self, demande):
        fragment = skills.registry.render('strategy.decision_reasoning', demande)
        assert fragment.content == _STRATEGE_SYSTEM

    @pytest.mark.parametrize('vide', ['', None])
    def test_une_demande_vide_ne_rend_rien(self, vide):
        fragment = skills.registry.render('strategy.decision_reasoning', vide)
        assert fragment.origin == 'none' and fragment.empty is True


class TestFicheASeptChamps:
    def test_les_six_champs_textuels_sont_renseignes(self):
        assert skills.registry.get('strategy.decision_reasoning').spec.is_fully_documented()

    def test_ne_requiert_aucune_information(self):
        assert skills.registry.get('strategy.decision_reasoning').spec.required_info == ()


class TestPipelineReelRebranche:
    """Preuve de bout en bout : le prompt réellement envoyé par `Stratege.run`
    commence par le texte exact du raisonnement stratégique."""

    def test_le_prompt_du_stratege_commence_par_le_raisonnement(self, monkeypatch):
        import agents.stratege as stratege

        prompts_captures = []

        def _capture_llm(prompt, max_tokens=5000, label=""):
            prompts_captures.append(prompt)
            return '{"strategie": {"decision_centrale": "x"}}'

        monkeypatch.setattr(stratege, '_call_llm', _capture_llm)
        monkeypatch.setattr(stratege, '_critique_strategie', lambda *a, **k: {})
        monkeypatch.setattr(stratege, '_load_rag_rules', lambda *a, **k: '')

        from agents.context import AnalysisContext
        ctx = AnalysisContext(comments=[], brain_context='Profil business',
                              video_context='', title='')
        ctx.add('psychologue', {'brief': {'insight': 'audience frustrée par le prix'}})

        stratege.Stratege().run(ctx)

        assert prompts_captures, "aucun appel LLM capturé"
        assert prompts_captures[0].startswith(_STRATEGE_SYSTEM)
