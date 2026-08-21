"""Équivalence de l'outil de classification d'intention.

`classify_intent` est déjà un classifieur déterministe réel, testé de longue
date. La comparaison porte directement sur des scénarios réels de conversation
Gabriel — pas des cas inventés pour l'occasion.
"""

import pytest

import tools as tools_pkg
from agents.orchestrator.intent import classify_intent


SCENARIOS = [
    ("Je veux comprendre ce que ressent mon audience", {}),
    ("Quelle est la bonne stratégie de positionnement ?", {'has_psycho': True}),
    ("Crée-moi un post LinkedIn", {'has_psycho': True, 'has_strategy': True}),
    ("Rédige une publicité", {'has_psycho': False, 'has_strategy': False}),
    ("Rédige une publicité", {'has_psycho': True, 'has_strategy': False}),
    ("Pourquoi cette stratégie est-elle la bonne ?", {'has_psycho': True, 'has_strategy': True}),
    ("Bonjour", {}),
    ("Salut", {}),
    ("Ma cible convient-elle à mon offre ?", {}),
    ('Analyse cette audience : https://youtu.be/abc123', {}),
    ("Je veux avancer", {}),
]


class TestEquivalenceAvecLaFonctionDOrigine:
    @pytest.mark.parametrize('message,kwargs', SCENARIOS)
    def test_loutil_rend_ce_que_classify_intent_rend(self, message, kwargs):
        attendu = classify_intent(message, **kwargs)
        obtenu = tools_pkg.registry.get('intent.classify').run(message=message, **kwargs)
        assert obtenu == attendu

    def test_un_lien_youtube_seul_est_oriente_vers_le_psychologue(self):
        obtenu = tools_pkg.registry.get('intent.classify').run(
            message='https://youtu.be/abc123')
        assert obtenu['agent'] == 'psychologue'

    def test_un_salut_bref_est_classe_greeting_sans_orientation(self):
        obtenu = tools_pkg.registry.get('intent.classify').run(message='Bonjour')
        assert obtenu['kind'] == 'greeting'
        assert obtenu['agent'] is None


class TestContrat:
    def test_le_contrat_se_declare_pur_sans_appel_reseau(self):
        spec = tools_pkg.registry.get('intent.classify').spec
        assert spec.deterministic is True
        assert spec.cacheable is True
        assert spec.timeout_s is None
