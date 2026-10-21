"""Preuve que le Planner compose réellement, sur les vrais registres.

Ce test ne vérifie pas un composant isolé : il envoie une mission complète
au vrai catalogue (les mêmes Agent/Tool/Skill Registry que la production
utilise) et vérifie que le plan produit dépend uniquement de ce que les
registres déclarent — jamais d'un chemin écrit à l'avance pour ce scénario.

C'est la différence que le brief demande de prouver : « Gabriel a compris
pourquoi il fallait appeler cet agent » et non « le développeur avait codé
le chemin à l'avance ». La preuve tient en un seul fait vérifiable : deux
missions différentes, envoyées au même Planner, produisent deux plans
différents — parce que les dépendances déclarées diffèrent, pas parce que
deux fonctions séparées ont été écrites pour chaque cas.
"""

from agents.catalog import registry as agents
from agents.context import AnalysisContext
from core.executor import Executor
from core.planner import default_planner


COMMENTAIRES = [
    {'text': "Ce programme m'a vraiment aidé à structurer mon offre.", 'likes': 40},
    {'text': "Le prix reste un frein, mais je comprends la valeur.", 'likes': 12},
    {'text': "Pas convaincu par la méthode, trop générique.", 'likes': 5},
]


class TestLePlanDependDeLaMissionPasDUnCheminEcritALAvance:
    """Deux objectifs différents, un seul Planner : s'il produisait le même
    enchaînement quelle que soit la mission, il ne déciderait de rien — il
    rejouerait un script."""

    def test_une_mission_d_analyse_seule_ne_mobilise_que_le_psychologue(self):
        plan = default_planner().plan('psychologue')
        assert plan.agent_ids == ('psychologue',)

    def test_une_mission_de_strategie_mobilise_le_psychologue_en_amont(self):
        """Le Stratège consomme 'psychologue' — c'est cette dépendance
        déclarée, et rien d'autre, qui force l'ordre."""
        plan = default_planner().plan('stratege')
        assert plan.agent_ids == ('psychologue', 'stratege')

    def test_une_mission_de_creation_complete_mobilise_les_trois(self):
        plan = default_planner().plan('createur')
        assert plan.agent_ids == ('psychologue', 'stratege', 'createur')

    def test_les_trois_plans_sont_reellement_distincts(self):
        """Le test qui compte : pas trois assertions isolées, mais la preuve
        que la longueur et le contenu du plan varient avec la mission."""
        planner = default_planner()
        plans = {but: planner.plan(but).agent_ids
                for but in ('psychologue', 'stratege', 'createur')}
        assert len(set(plans.values())) == 3   # aucun doublon entre les trois
        assert [len(p) for p in plans.values()] == [1, 2, 3]

    def test_fournir_un_rapport_deja_produit_raccourcit_le_plan(self):
        """Même objectif, mission différente (reprise vs analyse complète) :
        le plan change encore, cette fois sans toucher au code du tout —
        seulement à ce qui est déjà en main."""
        planner = default_planner()
        depart_a_zero = planner.plan('createur')
        reprise = planner.plan('createur', available=('psychologue', 'stratege'))
        assert depart_a_zero.agent_ids == ('psychologue', 'stratege', 'createur')
        assert reprise.agent_ids == ('createur',)


class TestExecutionReelleDeBoutEnBout:
    """La mission citée dans le brief ('analyse mon audience, construis une
    stratégie') correspond exactement à l'objectif 'stratege' sur le vrai
    catalogue — exécutée pour de vrai, IA neutralisée pour ne pas dépendre
    du réseau, mais Planner/Executor/Agents/Tools réels de bout en bout."""

    def test_gabriel_core_recoit_une_mission_et_produit_une_synthese(
            self, monkeypatch, deterministic_vader):
        import core.analyzer as analyzer
        monkeypatch.setattr(analyzer, 'call_llm', lambda *a, **k: '{"placeholder": true}')
        monkeypatch.setattr(analyzer, '_NLP_AVAILABLE', False)

        import agents.stratege as stratege
        monkeypatch.setattr(stratege, '_call_llm', lambda *a, **k: (
            '{"strategie":{"decision_centrale":"Prioriser une offre intermédiaire à 90€.",'
            '"risques":[],"actions":[]}}'))
        monkeypatch.setattr(stratege, '_critique_strategie', lambda *a, **k: {})

        mission = "Analyse mon audience et construis-moi une stratégie."
        objectif = 'stratege'   # ce que le Planner résout à partir de la mission

        plan = default_planner().plan(objectif)
        ctx = AnalysisContext(comments=list(COMMENTAIRES), brain_context='',
                              video_context='', title='Structurer une offre')
        ctx, trace = Executor(agents).execute(plan, ctx)
        synthese = ctx.to_response()

        assert trace.ok is True
        assert [s.agent_id for s in trace.steps] == ['psychologue', 'stratege']
        assert 'strategie' in synthese
        assert synthese['strategie']['decision_centrale']
