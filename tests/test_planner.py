"""Contrat du planificateur d'exécution.

Premier module qui *se sert* des registres pour décider. Il doit reproduire à
l'identique les enchaînements aujourd'hui écrits en dur, puis rendre explicites
les dépendances que le code actuel laisse à la charge de l'appelant.
"""

import pytest

from agents.registry import (STATUS_PLANNED, AgentNotFound, AgentRegistry,
                             AgentSpec)
from core.planner import (CircularDependency, Planner, UnreachableGoal,
                          default_planner)


@pytest.fixture
def planner():
    return default_planner()


class TestEquivalenceAvecLesPipelinesEcritsEnDur:
    """`core/orchestrator.py` expose deux pipelines figés. Le plan doit rendre
    exactement les mêmes enchaînements — sinon la couche ne décrit pas Gabriel,
    elle en décrit un autre."""

    def test_le_plan_du_psychologue_reproduit_run_psycho(self, planner):
        assert planner.plan('psychologue').agent_ids == ('psychologue',)

    def test_le_plan_du_stratege_avec_psycho_en_main_reproduit_run_stratege(self, planner):
        """`run_stratege` reçoit psycho_data et ne rejoue pas l'analyse."""
        plan = planner.plan('stratege', available=('psychologue',))
        assert plan.agent_ids == ('stratege',)
        assert plan.required_inputs == ()

    def test_le_plan_complet_enchaine_les_deux(self, planner):
        """Ce que le code actuel ne sait pas faire : personne ne relie les deux
        pipelines. C'est l'appelant qui doit y penser."""
        assert planner.plan('stratege').agent_ids == ('psychologue', 'stratege')


class TestDependancesRenduesExplicites:
    def test_le_stratege_ne_passe_jamais_avant_le_psychologue(self, planner):
        ids = planner.plan('createur').agent_ids
        assert ids.index('psychologue') < ids.index('stratege') < ids.index('createur')

    def test_les_entrees_a_fournir_sont_annoncees(self, planner):
        """« comments » n'est produit par aucun agent : c'est à l'appelant de
        le fournir. Le plan le dit avant de lancer quoi que ce soit de long."""
        assert planner.plan('psychologue').required_inputs == ('comments',)

    def test_une_dependance_deja_satisfaite_n_est_pas_rejouee(self, planner):
        """Rejouer une analyse déjà faite coûte du temps et de l'argent."""
        plan = planner.plan('createur', available=('psychologue', 'stratege'))
        assert plan.agent_ids == ('createur',)

    def test_chaque_etape_declare_son_vrai_point_d_entree(self, planner):
        """Le plan doit être exécutable tel quel : appeler `run` sur le Créateur
        échouerait."""
        etapes = {s.agent_id: s.entrypoint for s in planner.plan('createur')}
        assert etapes['createur'] == 'generate_script_or_text'
        assert etapes['psychologue'] == 'run'


class TestRefusExplicites:
    def test_un_objectif_non_implemente_est_refuse_avant_execution(self, planner):
        with pytest.raises(UnreachableGoal, match='architecte'):
            planner.plan('architecte')

    def test_un_objectif_inconnu_est_refuse(self, planner):
        with pytest.raises(AgentNotFound):
            planner.plan('le-stratege')

    def test_des_dependances_circulaires_sont_detectees_et_nommees(self):
        """Sans détection, la construction du plan partirait en récursion
        infinie — un plantage opaque au lieu d'un diagnostic."""
        r = AgentRegistry()
        r.register(AgentSpec(id='a', name='A', description='…',
                             consumes=('b_out',), produces='a_out'), loader=lambda: None)
        r.register(AgentSpec(id='b', name='B', description='…',
                             consumes=('a_out',), produces='b_out'), loader=lambda: None)
        with pytest.raises(CircularDependency, match='a → b → a'):
            Planner(r).plan('a')


class TestParallelisation:
    def _registre_en_y(self):
        """Deux analyses indépendantes, puis une synthèse qui les réunit."""
        r = AgentRegistry()
        for aid in ('gauche', 'droite'):
            r.register(AgentSpec(id=aid, name=aid.title(), description='…',
                                 consumes=('source',), produces=f'{aid}_out'),
                       loader=lambda: None)
        r.register(AgentSpec(id='synthese', name='Synthèse', description='…',
                             consumes=('gauche_out', 'droite_out'),
                             produces='synthese_out'), loader=lambda: None)
        return r

    def test_deux_etapes_independantes_sont_placees_dans_la_meme_vague(self):
        """Sans regroupement, tout plan s'exécuterait en série — y compris deux
        analyses qui ne dépendent l'une de l'autre en rien."""
        plan = Planner(self._registre_en_y()).plan('synthese')
        vagues = [[s.agent_id for s in v] for v in plan.waves()]
        assert vagues == [['droite', 'gauche'], ['synthese']]
        assert plan.parallelizable is True

    def test_une_chaine_lineaire_n_est_pas_annoncee_parallelisable(self, planner):
        assert planner.plan('stratege').parallelizable is False

    def test_la_synthese_attend_bien_ses_deux_sources(self):
        plan = Planner(self._registre_en_y()).plan('synthese')
        synthese = [s for s in plan if s.agent_id == 'synthese'][0]
        assert set(synthese.depends_on) == {'gauche', 'droite'}


class TestLisibilite:
    def test_le_plan_s_explique_en_clair(self, planner):
        texte = planner.explain('stratege')
        assert 'Le Psychologue' in texte and 'Le Stratège' in texte
        assert 'comments' in texte

    def test_le_plan_est_serialisable_pour_un_journal(self, planner):
        d = planner.plan('stratege').describe()
        assert d['waves'] == [['psychologue'], ['stratege']]
        assert d['required_inputs'] == ['comments']


class TestDependancesSouples:
    """Nuance tirée du code réel, pas d'un principe : `app.py` lance le Stratège
    sur un simple brief texte, sans analyse d'audience. Traiter cette
    dépendance comme dure ferait refuser un parcours qui fonctionne."""

    def test_le_plan_complet_passe_quand_meme_par_le_psychologue(self, planner):
        """Souple ne veut pas dire inutile : le meilleur chemin reste complet."""
        assert planner.plan('stratege').agent_ids == ('psychologue', 'stratege')

    def test_une_dependance_souple_non_productible_ne_bloque_pas(self):
        r = AgentRegistry()
        r.register(AgentSpec(id='psychologue', name='Le Psychologue',
                             description='…', produces='psychologue',
                             status=STATUS_PLANNED))
        r.register(AgentSpec(id='stratege', name='Le Stratège', description='…',
                             consumes=('psychologue',),
                             optional_consumes=('psychologue',),
                             produces='stratege'), loader=lambda: None)
        plan = Planner(r).plan('stratege')
        assert plan.required_inputs == ()             # rien ne bloque
        assert plan.optional_inputs == ('psychologue',)  # mais on le signale

    def test_une_dependance_souple_mais_satisfaite_nest_pas_dite_degradee(self, planner):
        """Défaut trouvé en simulant une mission réelle : le plan se déclarait
        dégradé alors que le Psychologue y figurait et tournait.

        `degraded_without` était rempli dès qu'une dépendance était *déclarée*
        souple, sans vérifier si une étape du plan la fournit. C'est l'erreur
        inverse de celle que ce champ doit empêcher — annoncer un résultat
        creux quand il est complet — et tout aussi trompeuse.
        """
        plan = planner.plan('stratege')
        assert plan.agent_ids == ('psychologue', 'stratege')
        for etape in plan:
            assert etape.degraded_without == (), (
                f"l'étape « {etape.agent_id} » se dit dégradée alors que le "
                f"plan fournit tout ce dont elle a besoin")

    def test_l_etape_dit_ce_dont_elle_se_passe_reellement(self):
        """Un exécutant doit pouvoir annoncer un résultat dégradé plutôt que de
        le présenter comme complet — mais seulement quand il l'est vraiment.

        Ce test figeait auparavant le contraire : il attendait que le Créateur
        se dise dégradé alors que le plan complet lui fournit Psychologue et
        Stratège. Il verrouillait le défaut au lieu de le détecter.
        """
        from agents.registry import STATUS_PLANNED, AgentRegistry, AgentSpec

        r = AgentRegistry()
        # Le fournisseur existe dans le catalogue mais n'est pas utilisable :
        # la dépendance souple manque donc réellement.
        r.register(AgentSpec(id='psychologue', name='P', description='…',
                             produces='psychologue', status=STATUS_PLANNED))
        r.register(AgentSpec(id='stratege', name='S', description='…',
                             consumes=('psychologue',),
                             optional_consumes=('psychologue',),
                             produces='stratege'), loader=lambda: None)

        etape = [s for s in Planner(r).plan('stratege')][0]
        assert etape.degraded_without == ('psychologue',)

    def test_une_entree_indispensable_reste_bloquante(self, planner):
        """Sans commentaires, il n'y a rien à analyser : cette dépendance-là
        n'est pas négociable."""
        assert planner.plan('psychologue').required_inputs == ('comments',)


class TestAgentsIndisponibles:
    def test_un_agent_en_panne_ne_sert_pas_de_fournisseur(self):
        """Si le Psychologue ne charge pas, le plan du Stratège ne doit pas
        prétendre l'appeler : son rapport devient une entrée à fournir."""
        r = AgentRegistry()
        r.register(AgentSpec(id='psychologue', name='Le Psychologue',
                             description='…', produces='psychologue',
                             status=STATUS_PLANNED))
        r.register(AgentSpec(id='stratege', name='Le Stratège', description='…',
                             consumes=('psychologue',), produces='stratege'),
                   loader=lambda: None)
        plan = Planner(r).plan('stratege')
        assert plan.agent_ids == ('stratege',)
        assert plan.required_inputs == ('psychologue',)


class TestUnPlanDitAussiAvecQuoi:
    """Exigence du brief : « Gabriel a compris pourquoi il fallait appeler cet
    agent, utiliser ce Skill et exécuter ces Tools dans cet ordre. »

    Un plan qui ne nomme que des agents ne répond qu'au premier tiers. Les
    outils et savoir-faire sont déclarés sur chaque agent depuis le début —
    ils étaient simplement invisibles dans le plan produit.
    """

    def test_chaque_etape_nomme_les_outils_de_son_agent(self, planner):
        etape = [s for s in planner.plan('psychologue')][0]
        assert etape.tools == ('audience.score_comments', 'audience.compute_kpis',
                              'audience.compute_dashboard')

    def test_chaque_etape_nomme_les_savoir_faire_de_son_agent(self, planner):
        etape = [s for s in planner.plan('psychologue')][0]
        assert etape.skills == ('psychology.human_understanding_grid',)

    def test_le_plan_agrege_les_capacites_de_toutes_ses_etapes(self, planner):
        plan = planner.plan('createur')
        # Le Créateur ne déclare aucun outil, le Psychologue et le Stratège si.
        assert 'audience.score_comments' in plan.tools
        assert 'adaptation.psycho_to_strategy_context' in plan.tools
        assert 'writing.human_voice' in plan.skills
        assert 'psychology.human_understanding_grid' in plan.skills

    def test_les_capacites_agregees_sont_sans_doublon(self):
        """Deux agents peuvent déclarer le même outil ; le plan ne doit pas le
        compter deux fois."""
        from agents.registry import AgentRegistry, AgentSpec
        from tools import registry as tool_registry

        r = AgentRegistry(tool_registry=tool_registry)
        r.register(AgentSpec(id='a', name='A', description='…',
                             consumes=('comments',), produces='a_out',
                             tools=('audience.score_comments',)),
                   loader=lambda: None)
        r.register(AgentSpec(id='b', name='B', description='…',
                             consumes=('a_out',), produces='b_out',
                             tools=('audience.score_comments',)),
                   loader=lambda: None)
        plan = Planner(r).plan('b')
        assert plan.tools == ('audience.score_comments',)

    def test_un_agent_sans_capacite_declaree_ne_casse_rien(self, planner):
        """Le Créateur ne déclare aucun outil : son étape doit rendre un tuple
        vide, pas manquer le champ."""
        createur = [s for s in planner.plan('createur') if s.agent_id == 'createur'][0]
        assert createur.tools == ()
        assert createur.skills != ()

    def test_lexplication_en_clair_nomme_les_capacites(self, planner):
        texte = planner.explain('stratege')
        assert 'outils :' in texte and 'méthodes :' in texte
        assert 'audience.score_comments' in texte
        assert 'strategy.decision_reasoning' in texte

    def test_le_plan_serialise_porte_les_capacites(self, planner):
        d = planner.plan('stratege').describe()
        assert 'tools' in d and 'skills' in d
        assert 'psychology.human_understanding_grid' in d['skills']
        assert 'tools' in d['steps'][0] and 'skills' in d['steps'][0]
