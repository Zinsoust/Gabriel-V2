"""Équivalence du Skill « structures de contenu » avec le catalogue d'origine.

`_SYSTEM_PROMPTS` porte à la fois la méthodologie (séquence obligatoire) et
le contrat de sortie (schéma JSON) — c'est le Skill le plus lourd extrait à
ce jour, et le premier dont le comportement de repli (format inconnu →
'hooks') diffère de celui d'`emotion_directive` (repli générique) et de
`tone_discipline` (repli vide).
"""

import pytest

import skills
from agents.createur import _FORMAT_LABEL, _SYSTEM_PROMPTS


ORTHOGRAPHES = [
    'hooks', 'HOOKS', ' hooks ', 'script', 'tiktok', 'reels', 'instagram',
    'youtube', 'post', 'linkedin', 'email', 'speech', 'discours', 'ad',
    'publicite', 'Script Vidéo', 'sales_page', 'angles',
]


class TestEquivalenceAvecLeCatalogue:
    @pytest.mark.parametrize('format_demande', sorted(_SYSTEM_PROMPTS))
    def test_chaque_format_du_catalogue_rend_son_prompt_exact(self, format_demande):
        assert skills.registry.render(
            'writing.content_structure', format_demande).content == \
            _SYSTEM_PROMPTS[format_demande]

    def test_les_variantes_de_casse_et_espaces_sont_absorbees(self):
        fragment = skills.registry.render('writing.content_structure', ' Script ')
        assert fragment.content == _SYSTEM_PROMPTS['script']
        assert fragment.known is True


class TestEquivalenceAvecLesDeuxSitesDAppelReels:
    """Reproduit exactement `fmt_key = (content_type or 'hooks').lower()...`
    puis `_SYSTEM_PROMPTS.get(fmt_key, _SYSTEM_PROMPTS['hooks'])`, tel qu'écrit
    aux deux endroits d'agents/createur.py — sans importer le Skill, pour que
    la comparaison ne soit pas tautologique."""

    @staticmethod
    def _comportement_historique(content_type):
        fmt_key = (content_type or 'hooks').lower().replace('-', '_').replace(' ', '_')
        return _SYSTEM_PROMPTS.get(fmt_key, _SYSTEM_PROMPTS['hooks'])

    @pytest.mark.parametrize('content_type', [
        None, '', 'hooks', 'Script', 'TIKTOK', 'format-inconnu', 'linkedin',
        'Sales Page',
    ])
    def test_le_skill_rend_le_meme_prompt_que_le_code_historique(self, content_type):
        assert skills.registry.render(
            'writing.content_structure', content_type).content == \
            self._comportement_historique(content_type)


class TestRepliVersHooksNEstPasPrisPourDuSavoirFaireReconnu:
    def test_un_format_inconnu_rend_bien_hooks(self):
        fragment = skills.registry.render('writing.content_structure', 'inexistant')
        assert fragment.content == _SYSTEM_PROMPTS['hooks']

    def test_mais_n_est_pas_declare_connu(self):
        """Contrairement à un vrai 'hooks' demandé explicitement — sinon un
        format mal orthographié passerait pour un format reconnu."""
        repli = skills.registry.render('writing.content_structure', 'inexistant')
        explicite = skills.registry.render('writing.content_structure', 'hooks')
        assert repli.known is False and repli.origin == 'default'
        assert explicite.known is True and explicite.origin == 'catalog'
        assert repli.content == explicite.content   # même texte, statut différent


class TestFicheASeptChamps:
    def test_les_sept_champs_sont_reellement_renseignes(self):
        spec = skills.registry.get('writing.content_structure').spec
        assert spec.is_fully_documented()

    def test_la_fiche_liste_les_15_formats_couverts(self):
        description = skills.registry.get('writing.content_structure').describe()
        assert set(description['keys']) == set(_SYSTEM_PROMPTS)


class TestPipelineReelRebranche:
    """`generate_script_or_text` construit maintenant son prompt via le Skill.
    Preuve de bout en bout : le texte de structure envoyé au modèle est
    encore exactement celui du catalogue — pas seulement l'appel isolé."""

    def test_le_prompt_final_contient_le_bon_bloc_de_structure(self, monkeypatch):
        import agents.createur as createur

        prompts_captures = []

        def _capture_llm(prompt, max_tokens=3000, temperature=None):
            prompts_captures.append(prompt)
            return '{"hooks": []}'

        monkeypatch.setattr(createur, '_call_llm', _capture_llm)
        monkeypatch.setattr(createur.Createur, 'retrieve_creator_rag_context',
                            lambda self, *a, **k: ('', []))

        createur.Createur().generate_script_or_text(
            content_type='linkedin', psycho_data={}, strategy={})

        assert prompts_captures, "aucun appel LLM capturé"
        assert prompts_captures[0].startswith(_SYSTEM_PROMPTS['linkedin'])
