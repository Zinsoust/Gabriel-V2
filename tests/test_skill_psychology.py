"""Équivalence de la grille de compréhension humaine.

`GABRIEL_SYSTEM` n'a pas de variante : c'est un cadre unique et obligatoire.
Le test central n'est donc pas « bonne variante choisie » (il n'y en a
qu'une) mais « le texte injecté n'a pas bougé d'un caractère », sur les
cinq sites d'appel réels du Psychologue.
"""

import pytest

import skills
from core.analyzer import GABRIEL_SYSTEM


class TestEquivalenceAvecLaConstanteDOrigine:
    @pytest.mark.parametrize('demande', ['psychologue', 'autre chose', 'x'])
    def test_toute_demande_non_vide_rend_toujours_le_meme_texte(self, demande):
        """Contrairement aux Skills d'écriture, il n'y a rien à choisir ici :
        n'importe quelle demande non vide doit rendre le même cadre — le
        Skill s'applique, il ne sélectionne pas."""
        fragment = skills.registry.render('psychology.human_understanding_grid', demande)
        assert fragment.content == GABRIEL_SYSTEM

    @pytest.mark.parametrize('vide', ['', None])
    def test_une_demande_vide_suit_la_regle_commune_a_tous_les_skills(self, vide):
        """`CatalogSkill.normalize()` court-circuite une demande vide avant
        d'appeler le normaliseur propre à ce Skill — cohérent avec
        writing.tone_discipline et writing.emotion_directive. Ce Skill
        s'invoque donc avec une clé fixe non vide (ex. 'psychologue'), jamais
        avec une chaîne vide."""
        fragment = skills.registry.render('psychology.human_understanding_grid', vide)
        assert fragment.origin == 'none'
        assert fragment.empty is True

    def test_le_fragment_est_bien_marque_connu(self):
        fragment = skills.registry.render('psychology.human_understanding_grid', 'psychologue')
        assert fragment.known is True
        assert fragment.origin == 'catalog'


class TestFicheASeptChamps:
    def test_les_sept_champs_sont_renseignes(self):
        spec = skills.registry.get('psychology.human_understanding_grid').spec
        assert spec.is_fully_documented()

    def test_ne_requiert_aucune_information(self):
        """Cadre universel, pas paramétré par l'analyse en cours."""
        spec = skills.registry.get('psychology.human_understanding_grid').spec
        assert spec.required_info == ()


class TestPipelineReelRebranche:
    """`core/analyzer.py` a cinq sites d'appel qui interpolaient directement
    GABRIEL_SYSTEM ; ils passent maintenant par `_psychology_grid()`, qui
    lit le Skill. Preuve de bout en bout : chaque prompt réellement envoyé
    au modèle, sur le vrai pipeline, commence toujours par le même texte."""

    COMMENTAIRES = [
        {"text": "Ce programme m'a vraiment aidé à structurer mon offre.", "likes": 40},
        {"text": "Le prix reste un frein, mais je comprends la valeur.", "likes": 12},
        {"text": "Pas convaincu par la méthode, trop générique.", "likes": 5},
        {"text": "Excellent accompagnement, résultats concrets rapidement.", "likes": 28},
        {"text": "Le support client est lent à répondre, dommage.", "likes": 7},
    ]

    # Labels call_llm des cinq fonctions rebranchées — main_a/main_b viennent
    # toutes deux de _analyze_main (deux appels parallèles). D'autres appels
    # du pipeline (interp_psycho, interp_socio) construisent leur propre
    # prompt à partir des cartes RAG, sans jamais utiliser la grille : ce
    # n'est pas une omission du rebranchement, c'est le comportement
    # d'origine, donc ils sont exclus de cette vérification.
    LABELS_REBRANCHES = {'main_a', 'main_b', 'recommandations', 'brief', 'livrables_ia'}

    def test_chaque_prompt_rebranche_commence_par_la_grille(self, monkeypatch):
        import core.analyzer as analyzer

        prompts_captures = []

        def _capture_llm(prompt, max_tokens=1500, label='', fast=False):
            prompts_captures.append((label, prompt))
            return '{"placeholder": true}'

        monkeypatch.setattr(analyzer, 'call_llm', _capture_llm)
        monkeypatch.setattr(analyzer, '_NLP_AVAILABLE', False)

        analyzer.analyze_comments(list(self.COMMENTAIRES), title='Structurer une offre')

        pertinents = [(label, prompt) for label, prompt in prompts_captures
                     if label in self.LABELS_REBRANCHES or label.startswith('persona[')]
        assert len(pertinents) >= 4, (
            f"seulement {len(pertinents)} appels pertinents capturés parmi "
            f"{[l for l, _ in prompts_captures]} — le pipeline n'a pas "
            "exercé les fonctions attendues")
        for label, prompt in pertinents:
            assert prompt.startswith(GABRIEL_SYSTEM), (
                f"le prompt « {label} » ne commence plus par la grille "
                "psychologique — le rebranchement a rompu quelque chose")
