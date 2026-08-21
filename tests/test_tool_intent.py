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


class TestSelectionDesRapportsARelire:
    """`plan_context_access` décide quels rapports une demande justifie de
    relire. Le défaut par défaut est *aucun* : traiter un rapport comme un
    contexte implicite à chaque message alourdirait chaque échange et
    masquerait d'où vient une recommandation."""

    DISPO = {'psychologue': True, 'stratege': True, 'createur': True}

    def _plan(self, message, intent=None, memory=None):
        from agents.orchestrator.intent import classify_intent
        return tools_pkg.registry.get('intent.plan_context_access').run(
            message=message, intent=intent or classify_intent(message),
            availability=self.DISPO, memory=memory)

    def test_loutil_rend_ce_que_la_fonction_rend(self):
        from agents.orchestrator.context_access import plan_context_access
        from agents.orchestrator.intent import classify_intent

        message = "Est-ce cohérent avec ce que dit le psychologue ?"
        intent = classify_intent(message)
        attendu = plan_context_access(message, intent, self.DISPO, None)
        assert self._plan(message, intent) == attendu

    def test_une_demande_ordinaire_nouvre_aucun_rapport(self):
        """La garantie qui compte : une simple question ne déclenche pas la
        relecture de tout ce qui a été produit."""
        resultat = self._plan("Comment je devrais m'y prendre ?")
        assert resultat['use_agent_context'] is False
        assert resultat['agents'] == []

    def test_une_demande_de_synthese_ouvre_tous_les_rapports(self):
        resultat = self._plan("Fais-moi une synthèse de tout ce qu'on a")
        assert resultat['use_agent_context'] is True
        assert set(resultat['agents']) == set(self.DISPO)

    def test_une_reference_explicite_nouvre_que_lagent_cite(self):
        resultat = self._plan("Que disait le psychologue sur cette audience ?")
        assert resultat['agents'] == ['psychologue']

    def test_une_relance_courte_retrouve_les_rapports_du_tour_precedent(self):
        """« Est-ce cohérent ? » ne dit pas de quoi on parle. Sans la mémoire
        du tour précédent, cette relance n'ouvrirait rien — ou pire, ouvrirait
        tout. Elle ne doit rouvrir que ce qui a réellement été consulté."""
        # « cohérent » est déjà classé transversal en amont et ouvre tout ;
        # c'est une relance sans mot-clé, comme « Pourquoi ? », qui emprunte
        # réellement le chemin de la mémoire.
        avec_memoire = self._plan(
            "Pourquoi ?", memory={'last_context_agents': ['psychologue']})
        sans_memoire = self._plan("Pourquoi ?")

        assert avec_memoire['agents'] == ['psychologue']
        assert avec_memoire['reason'] == 'conversation_follow_up'
        assert sans_memoire['agents'] == []

    def test_sans_aucun_rapport_disponible_rien_nest_ouvert(self):
        from agents.orchestrator.intent import classify_intent
        message = "Fais-moi une synthèse"
        resultat = tools_pkg.registry.get('intent.plan_context_access').run(
            message=message, intent=classify_intent(message),
            availability={'psychologue': False, 'stratege': False, 'createur': False})
        assert resultat['reason'] == 'no_available_outputs'


class TestPassageDeRelais:
    def test_loutil_rend_ce_que_la_fonction_rend(self):
        from agents.orchestrator.intent import build_handoff

        args = dict(agent='psychologue', message="Analyse mon audience",
                   business_context={'activite': 'Coaching'}, has_psycho=False,
                   has_strategy=False)
        attendu = build_handoff(**args)
        assert tools_pkg.registry.get('intent.build_handoff').run(**args) == attendu

    def test_le_paquet_ne_transporte_que_lutile(self):
        """Contrat du brief fondateur : compact, sérialisable, jamais
        l'historique brut."""
        paquet = tools_pkg.registry.get('intent.build_handoff').run(
            agent='stratege', message="Quelle offre construire ?",
            business_context={'activity': 'Coaching', 'offer': 'Programme'},
            has_psycho=True)
        assert paquet['target_agent'] == 'stratege'
        assert paquet['known_context']['activite'] == 'Coaching'
        assert paquet['upstream_done'] == {'psychologue': True, 'stratege': False}

    def test_les_deux_conventions_de_nommage_du_contexte_sont_lues(self):
        """Le contexte business existe en clés françaises (profil hérité) et
        anglaises (Entretien stratégique) — ignorer l'une donnerait un paquet
        vide pour la moitié des comptes."""
        outil = tools_pkg.registry.get('intent.build_handoff')
        fr = outil.run(agent='createur', message='x', business_context={'offre': 'A'})
        en = outil.run(agent='createur', message='x', business_context={'offer': 'A'})
        assert fr['known_context']['offre'] == en['known_context']['offre'] == 'A'

    def test_un_message_tres_long_est_borne(self):
        paquet = tools_pkg.registry.get('intent.build_handoff').run(
            agent='psychologue', message='x' * 2000)
        assert len(paquet['user_goal']) == 400
