"""Contrat du registre de savoir-faire.

Le registre existe pour que le Core puisse répondre à « Gabriel maîtrise-t-il
ceci ? » avant d'agir, au lieu de le découvrir dans la qualité du résultat.
"""

import pytest

import skills
from skills import CatalogSkill, SkillSpec
from skills.registry import SkillNotFound, SkillRegistry


def _skill(sid='test.methode', **kw):
    spec = SkillSpec(id=sid, name='Méthode test', description='…',
                     domain=kw.pop('domain', 'test'))
    return CatalogSkill(spec=spec, catalog={'a': 'BLOC A', 'b': 'BLOC B'},
                        aliases={'alpha': 'a'}, **kw)


class TestHonneteteSurLIgnorance:
    """Le défaut que cette couche corrige : le code historique renvoyait une
    chaîne vide pour une tonalité inconnue — indiscernable d'un savoir-faire
    qui n'a rien à ajouter. Le Core ne pouvait donc pas savoir qu'il promettait
    quelque chose que Gabriel ne sait pas faire."""

    def test_un_savoir_faire_connu_est_signale_comme_tel(self):
        fragment = _skill().render('a')
        assert fragment.known is True and fragment.origin == 'catalog'

    def test_un_savoir_faire_inconnu_est_signale_comme_tel(self):
        fragment = _skill().render('notarial')
        assert fragment.known is False
        assert fragment.origin == 'none'
        assert fragment.empty is True

    def test_un_repli_ne_se_fait_pas_passer_pour_du_savoir_faire(self):
        fragment = _skill(fallback=lambda x: f'GABARIT {x}').render('notarial')
        assert fragment.origin == 'fallback'
        assert fragment.known is False   # du texte, mais pas une méthode
        assert fragment.empty is False

    def test_covers_repond_avant_l_action(self):
        s = _skill()
        assert s.covers('a') and s.covers('alpha') and not s.covers('notarial')

    def test_le_fragment_garde_la_trace_de_ce_qui_a_ete_demande(self):
        """Pour qu'un journal d'exécution montre l'écart entre la demande de
        l'utilisateur et la clé réellement appliquée."""
        fragment = _skill().render('ALPHA')
        assert fragment.requested == 'ALPHA' and fragment.key == 'a'


class TestRegistre:
    def test_un_identifiant_en_double_est_refuse(self):
        r = SkillRegistry()
        r.register(_skill())
        with pytest.raises(ValueError, match='déjà enregistré'):
            r.register(_skill())

    def test_skill_inconnu_liste_les_skills_connus(self):
        r = SkillRegistry()
        r.register(_skill())
        with pytest.raises(SkillNotFound, match='test.methode'):
            r.get('test.absent')

    def test_filtrage_par_domaine(self):
        r = SkillRegistry()
        r.register(_skill('w.un', domain='writing'))
        r.register(_skill('s.un', domain='strategy'))
        assert r.domains() == ('strategy', 'writing')
        assert [s.spec.id for s in r.by_domain('writing')] == ['w.un']


class TestCatalogueLisibleParLeCore:
    def test_un_skill_enumere_ce_qu_il_couvre(self):
        """Sans cela, aucun planificateur ne peut savoir si Gabriel sait écrire
        en « ton premium » avant de le promettre."""
        description = skills.registry.get('writing.tone_discipline').describe()
        assert 'premium' in description['keys']
        assert description['domain'] == 'writing'

    def test_la_description_dit_ou_vit_la_methodologie(self):
        """Traçabilité : un savoir-faire déclaré doit pouvoir être retrouvé."""
        for description in skills.registry.describe():
            assert description['source'], description['id']

    def test_les_deux_savoir_faire_d_ecriture_sont_disponibles(self):
        assert 'writing.tone_discipline' in skills.registry
        assert 'writing.emotion_directive' in skills.registry
