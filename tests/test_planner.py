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

    def test_l_etape_dit_ce_dont_elle_se_passe(self, planner):
        """Un exécutant doit pouvoir annoncer un résultat dégradé plutôt que de
        le présenter comme complet."""
        etape = [s for s in planner.plan('createur') if s.agent_id == 'createur'][0]
        assert set(etape.degraded_without) == {'psychologue', 'stratege'}

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
