"""Voix humaine — la seule méthodologie de Gabriel écrite deux fois.

Une fois en consigne injectée au modèle, une fois en validateur regex
(`content_quality.check`). Ce fichier prouve l'équivalence de l'extraction,
puis **fige la divergence mesurée** entre les deux implémentations : elle
est réelle, elle n'est pas corrigée ici, et elle ne doit pas s'aggraver
sans que quelqu'un le voie.
"""

import pytest

import skills
import tools as tools_pkg
from agents.createur import _HUMAN_VOICE


class TestEquivalenceAvecLaConstanteDOrigine:
    @pytest.mark.parametrize('demande', ['createur', 'autre', 'x'])
    def test_toute_demande_non_vide_rend_le_meme_texte(self, demande):
        assert skills.registry.render('writing.human_voice', demande).content == _HUMAN_VOICE

    def test_le_bloc_porte_bien_ses_trois_composants(self):
        """Formules interdites, test par phrase, ancrage dans les mots réels —
        retirer l'un d'eux viderait la méthode de sa substance."""
        contenu = skills.registry.render('writing.human_voice', 'createur').content
        assert 'INTERDIT' in contenu
        assert 'TEST PAR PHRASE' in contenu
        assert 'ANCRAGE RÉEL' in contenu


class TestPipelineReelRebranche:
    def test_le_prompt_du_createur_contient_la_voix_humaine(self, monkeypatch):
        import agents.createur as createur

        prompts = []

        def _capture(prompt, max_tokens=3000, temperature=None):
            prompts.append(prompt)
            return '{"hooks": []}'

        monkeypatch.setattr(createur, '_call_llm', _capture)
        monkeypatch.setattr(createur.Createur, 'retrieve_creator_rag_context',
                            lambda self, *a, **k: ('', []))

        createur.Createur().generate_script_or_text(
            content_type='hooks', psycho_data={}, strategy={})

        assert prompts, "aucun appel LLM capturé"
        assert _HUMAN_VOICE in prompts[0]


class TestDivergenceMesureeEntreLaConsigneEtSonValidateur:
    """Six interdictions du texte ne sont vérifiées par aucune regex.

    Ce n'est pas une supposition : chaque phrase ci-dessous est soumise au
    vrai validateur de production. Le test fige l'écart tel qu'il est
    aujourd'hui — le corriger changerait le taux de rejet du contrôle
    qualité, ce qui mérite sa propre décision.
    """

    # Trois angles morts ont été fermés — des formules d'ouverture sans usage
    # légitime en contenu marketing, mesurées à zéro faux positif.
    FERMES = [
        "bonjour à tous et bienvenue dans cette nouvelle vidéo de la chaîne",
        "bienvenue sur ma chaîne, ravi de vous retrouver pour ce sujet précis",
        "nous vivons dans une époque troublée où tout change très vite ici",
    ]

    # Trois restent ouverts, et pour une raison mesurée : ces tournures sont du
    # vocabulaire marketing français courant. Les détecter signalerait comme
    # artificiel un texte parfaitement légitime.
    ANGLES_MORTS = [
        "il faut se transformer profondément pour avancer dans ce projet précis",
        "devenir la meilleure version de soi demande du travail quotidien réel",
        "le chemin sera long mais le parcours en vaut vraiment la peine ici",
    ]

    # Copies légitimes qui contiennent ces mêmes tournures : elles ne doivent
    # jamais être signalées. C'est cette contrainte qui interdit de fermer les
    # trois angles morts restants.
    LEGITIMES = [
        "Le parcours client de mes prospects s'arrête toujours au moment du prix",
        "La meilleure version de ton offre est celle que tes clients réclament",
        "J'ai réduit le chemin entre la découverte et l'achat à trois étapes",
    ]
    DETECTEES = [
        "il est temps de passer à l'action maintenant sans plus attendre du tout",
        "libérer ton potentiel dès maintenant est la seule chose qui compte ici",
        "n'hésitez pas à me contacter si le sujet vous intéresse vraiment ici",
    ]

    def _ai_free(self, phrase):
        return tools_pkg.registry.get('content_quality.check').run(
            content_result={'texte': phrase}, psycho_data={}, strategy={},
            content_type='post')['ai_free']

    @pytest.mark.parametrize('phrase', DETECTEES)
    def test_les_formules_couvertes_sont_bien_rejetees(self, phrase):
        assert self._ai_free(phrase) is False

    @pytest.mark.parametrize('phrase', FERMES)
    def test_les_angles_morts_fermes_sont_desormais_detectes(self, phrase):
        """Trois interdictions de la consigne que le validateur ignorait sont
        maintenant vérifiées. Ce n'était sans risque que parce qu'elles n'ont
        aucun usage légitime en contenu marketing."""
        assert self._ai_free(phrase) is False

    @pytest.mark.parametrize('phrase', ANGLES_MORTS)
    def test_les_angles_morts_restants_passent_encore(self, phrase):
        """Écart assumé, pas oublié : fermer ceux-ci signalerait du texte
        légitime — voir le test suivant, qui en est la raison."""
        assert self._ai_free(phrase) is True

    @pytest.mark.parametrize('phrase', LEGITIMES)
    def test_une_copie_legitime_nest_jamais_signalee(self, phrase):
        """La contrainte qui interdit d'aller plus loin. « Le parcours
        client », « la meilleure version de ton offre » sont du vocabulaire
        marketing français courant : un détecteur qui les rejette nuit plus
        que le défaut qu'il cherche."""
        assert self._ai_free(phrase) is True

    def test_toutes_les_formules_interdites_figurent_bien_dans_la_consigne(self):
        """La consigne, elle, les couvre toutes — c'est le validateur qui est
        en retard, pas le texte."""
        consigne = _HUMAN_VOICE.lower()
        for extrait in ('se transformer', 'meilleure version', 'bonjour à tous',
                       'bienvenue sur', "nous vivons dans une époque", 'chemin'):
            assert extrait in consigne, extrait


class TestFicheASeptChamps:
    def test_les_six_champs_textuels_sont_renseignes(self):
        assert skills.registry.get('writing.human_voice').spec.is_fully_documented()

    def test_le_skill_declare_son_validateur(self):
        """`allowed_tools` relie la méthode au Tool qui la vérifie — c'est ce
        qui rend la divergence traçable plutôt qu'invisible."""
        assert skills.registry.get('writing.human_voice').spec.allowed_tools == \
            ('content_quality.check',)

    def test_la_fiche_declare_explicitement_la_divergence(self):
        limitations = skills.registry.get('writing.human_voice').spec.limitations
        assert 'diverg' in limitations.lower()
