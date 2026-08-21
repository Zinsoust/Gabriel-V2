"""Immersion persona — la méthode devient visible, l'assemblage reste en place.

Dernier savoir-faire de l'ordre d'extraction de l'audit. Sa particularité :
la méthode n'est pas un texte fixe mais dix angles assemblés depuis les
données du Psychologue. Seul le cadrage est extrait ; l'assemblage reste dans
`build_writing_brief`, où il fonctionne.
"""

import pytest

import skills
from agents.createur import _PERSONA_IMMERSION


class TestEquivalenceAvecLaConstanteDOrigine:
    @pytest.mark.parametrize('demande', ['createur', 'autre', 'x'])
    def test_toute_demande_non_vide_rend_le_meme_cadrage(self, demande):
        assert skills.registry.render(
            'writing.persona_immersion', demande).content == _PERSONA_IMMERSION

    def test_le_cadrage_porte_la_regle_qui_fait_la_methode(self):
        """« Elle n'est pas ton audience » est ce qui distingue écrire *depuis*
        une personne d'écrire *sur* elle — retirer cette phrase viderait la
        méthode de sa substance."""
        contenu = skills.registry.render('writing.persona_immersion', 'createur').content
        assert "n'est pas ton audience" in contenu
        assert "2 ans en arrière" in contenu


class TestPipelineReelRebranche:
    """`build_writing_brief` construit le brief ligne à ligne ; son en-tête
    d'immersion passe maintenant par le Skill."""

    PSYCHO = {
        'psychologie': {
            'frustrations': ['perdre des heures sur des tâches sans valeur'],
            'desirs_caches': ['être pris au sérieux'],
            'motivations_profondes': ['bâtir quelque chose qui dure'],
            'objections_principales': ["je n'ai pas le temps"],
        },
        'emotions': {'repartition': [{'emotion': 'Espoir'}],
                     'espoir_decu': 'une méthode promise qui n\'a rien changé'},
        'brief': {'synthese': 'Audience compétente mais épuisée',
                  'insight_cle': 'Le manque de temps cache une peur de mal faire'},
        'marketing': {},
        # Alimente l'angle « Ses mots à elle » — sans cette donnée, l'angle est
        # (correctement) omis du brief.
        'nlp': {'mots_frequents': ['temps', 'méthode', 'concret']},
    }

    def _brief(self, persona=None):
        from agents.createur import Createur
        return Createur().build_writing_brief(
            content_type='hooks', channel='', tone='', objective='',
            psycho_data=self.PSYCHO, strategy={}, persona=persona,
            business_context={}, user_request='')

    def test_le_brief_contient_le_cadrage_issu_du_skill(self):
        assert _PERSONA_IMMERSION in self._brief()

    def test_les_angles_nourris_par_les_donnees_suivent_le_cadrage(self):
        """Le Skill déclare la méthode ; l'assemblage reste dans le Créateur.
        Ce test vérifie que les deux se rejoignent bien dans le brief réel."""
        brief = self._brief()
        for angle in ("Ce qui l'épuise chaque jour",
                     "Ce qu'elle espérait et qui ne s'est pas passé",
                     "Ses mots à elle",
                     "La vérité qu'elle ne s'est jamais dite à elle-même"):
            assert angle in brief, angle

    def test_un_angle_sans_donnee_est_omis_et_non_rendu_vide(self):
        """Comportement d'origine conservé : un rapport pauvre produit une
        immersion pauvre, pas une section à trous."""
        from agents.createur import Createur
        brief = Createur().build_writing_brief(
            content_type='hooks', channel='', tone='', objective='',
            psycho_data={}, strategy={}, persona=None,
            business_context={}, user_request='')
        assert _PERSONA_IMMERSION in brief
        assert "Ce qui l'épuise chaque jour" not in brief


class TestFicheASeptChamps:
    def test_les_six_champs_textuels_sont_renseignes(self):
        assert skills.registry.get('writing.persona_immersion').spec.is_fully_documented()

    def test_cest_le_seul_skill_dont_les_besoins_en_donnees_sont_reels(self):
        """Les autres Skills s'appliquent tels quels ; celui-ci ne vaut que
        par les données qui le nourrissent — sa fiche doit le dire."""
        spec = skills.registry.get('writing.persona_immersion').spec
        assert len(spec.required_info) >= 9
        assert 'brief.insight_cle' in spec.required_info

    def test_la_fiche_declare_ce_qui_nest_pas_extrait(self):
        limitations = skills.registry.get('writing.persona_immersion').spec.limitations
        assert 'build_writing_brief' in limitations
