"""Contrat de l'exécuteur de plans.

Pièce la plus risquée de la migration : elle lance réellement les agents. Le
premier devoir des tests est donc de prouver qu'elle produit le même résultat
que les pipelines écrits en dur — avant d'envisager de rebrancher quoi que ce
soit dessus.
"""

import pytest

from agents.context import AnalysisContext
from agents.registry import AgentRegistry, AgentSpec
from core.executor import (Executor, ExecutionError, MissingInputs,
                           NotExecutable, STEP_OK)
from core.planner import Planner, default_planner


# ── Agents factices : pas de réseau, pas d'IA, comportement contrôlé ─────────

def _agent_factice(agent_id, produit, journal=None, casse=False):
    class _Factice:
        AGENT_ID = agent_id

        def run(self, ctx):
            if journal is not None:
                journal.append(agent_id)
            if casse:
                raise ValueError(f"panne simulée de {agent_id}")
            ctx.add(agent_id, {produit: f'valeur de {agent_id}'})
            return ctx
    return _Factice


def _contexte(comments=None):
    return AnalysisContext(comments=comments if comments is not None else ['a'],
                           brain_context='', video_context='', title='')


def _registre_chaine(journal=None, casse=()):
    """amont → aval, l'aval dépendant de l'amont."""
    r = AgentRegistry()
    r.register(AgentSpec(id='amont', name='Amont', description='…',
                         consumes=('comments',), produces='amont'),
               loader=lambda: _agent_factice('amont', 'a', journal, 'amont' in casse))
    r.register(AgentSpec(id='aval', name='Aval', description='…',
                         consumes=('amont',), produces='aval'),
               loader=lambda: _agent_factice('aval', 'b', journal, 'aval' in casse))
    return r


class TestEquivalenceAvecLAppelDirect:
    """Référence indépendante : l'agent appelé à la main.

    `Gabriel.run_psycho` passe désormais par l'exécuteur — le comparer à
    l'exécuteur ne prouverait plus rien. La comparaison porte donc sur
    l'invocation directe de l'agent, qui ne dépend d'aucune des deux couches.
    """

    COMMENTAIRES = [
        {'text': "Merci, ça m'a débloqué.", 'likes': 12},
        {'text': 'Pas convaincu du tout.', 'likes': 3},
        {'text': 'Le prix me freine.', 'likes': 7},
    ]

    @staticmethod
    def _sans_ia(monkeypatch):
        import core.analyzer as analyzer
        monkeypatch.setattr(analyzer, 'call_llm', lambda *a, **k: '{"placeholder": true}')
        monkeypatch.setattr(analyzer, '_NLP_AVAILABLE', False)

    @staticmethod
    def _sans_duree(resultat):
        """`_timing` contient des durées mesurées : deux exécutions ne peuvent
        pas les avoir identiques."""
        return {k: v for k, v in resultat.items() if k != '_timing'}

    def test_le_plan_du_psychologue_rend_ce_que_l_agent_rend_seul(
            self, monkeypatch, deterministic_vader):
        from agents.psychologue import Psychologue

        self._sans_ia(monkeypatch)
        reference = AnalysisContext(comments=list(self.COMMENTAIRES), brain_context='',
                                    video_context='', title='Offre')
        Psychologue().run(reference)

        ctx = AnalysisContext(comments=list(self.COMMENTAIRES), brain_context='',
                              video_context='', title='Offre')
        _, trace = Executor().execute(default_planner().plan('psychologue'), ctx)

        assert ctx.to_response().keys() == reference.to_response().keys()
        assert self._sans_duree(ctx.to_response()) == self._sans_duree(reference.to_response())
        assert trace.ok is True
        assert [s.agent_id for s in trace.steps] == ['psychologue']

    def test_le_pipeline_public_rend_toujours_la_meme_chose(
            self, monkeypatch, deterministic_vader):
        """`run_psycho` est le point d'entrée utilisé par app.py : son contenu
        ne doit pas avoir bougé d'un caractère avec le rebranchement."""
        from agents.psychologue import Psychologue
        from core.orchestrator import Gabriel

        self._sans_ia(monkeypatch)
        reference = AnalysisContext(comments=list(self.COMMENTAIRES), brain_context='',
                                    video_context='', title='Offre')
        Psychologue().run(reference)

        obtenu = Gabriel().run_psycho(list(self.COMMENTAIRES), title='Offre')
        assert self._sans_duree(obtenu) == self._sans_duree(reference.to_response())

    def test_le_pipeline_strategique_ne_rejoue_pas_le_psychologue(self, monkeypatch):
        """`run_stratege` reçoit un rapport déjà produit : le plan doit s'en
        contenter, sinon chaque stratégie relancerait une analyse complète."""
        from core.orchestrator import Gabriel

        appels = []

        class _StrategeFactice:
            AGENT_ID = 'stratege'
            AGENT_NAME = 'Le Stratège'

            def run(self, ctx):
                appels.append(ctx.get('psychologue'))
                ctx.add('stratege', {'strategie': {'ok': True}})
                return ctx

        import agents.catalog as catalog
        monkeypatch.setattr(catalog.registry.get('stratege'), 'loader',
                            lambda: _StrategeFactice)

        rapport = {'brief': {'insight': 'audience frustrée'}}
        resultat = Gabriel().run_stratege(rapport, brain_context='profil')

        assert appels == [rapport]          # le rapport fourni est bien lu, non rejoué
        # `to_response` fusionne toutes les contributions : le rapport
        # psychologique ressort avec la stratégie. app.py en dépend.
        assert resultat == {'brief': {'insight': 'audience frustrée'},
                            'strategie': {'ok': True}}


class TestOrdreEtDependances:
    def test_les_etapes_s_executent_dans_l_ordre_du_plan(self):
        journal = []
        registre = _registre_chaine(journal)
        plan = Planner(registre).plan('aval')
        Executor(registre).execute(plan, _contexte())
        assert journal == ['amont', 'aval']

    def test_l_aval_lit_bien_ce_que_l_amont_a_depose(self):
        """Sans ce passage de main, chaque agent tournerait à vide."""
        registre = _registre_chaine()
        ctx, _ = Executor(registre).execute(Planner(registre).plan('aval'), _contexte())
        assert ctx.get('amont') == {'a': 'valeur de amont'}
        assert ctx.get('aval') == {'b': 'valeur de aval'}


class TestRefusAvantDepense:
    def test_une_entree_indispensable_manquante_arrete_avant_de_lancer(self):
        """Sans commentaires, l'analyse ne produirait pas une erreur franche
        mais un résultat vide qui ressemble à un résultat."""
        registre = _registre_chaine()
        journal = []
        registre_journal = _registre_chaine(journal)
        with pytest.raises(MissingInputs, match='comments'):
            Executor(registre_journal).execute(
                Planner(registre_journal).plan('aval'), _contexte(comments=[]))
        assert journal == []   # rien n'a tourné

    def test_une_etape_hors_protocole_est_refusee_explicitement(self):
        """Le Créateur s'appelle `generate_script_or_text` : un plan ne peut pas
        l'exécuter. Le dire vaut mieux que d'échouer sur un AttributeError."""
        with pytest.raises(NotExecutable, match='generate_script_or_text'):
            Executor().check(default_planner().plan('createur'), _contexte())

    def test_la_verification_precede_toute_execution(self):
        """Une étape non exécutable en fin de plan ne doit pas laisser les
        premières étapes tourner pour rien."""
        journal = []
        r = AgentRegistry()
        r.register(AgentSpec(id='amont', name='Amont', description='…',
                             consumes=('comments',), produces='amont'),
                   loader=lambda: _agent_factice('amont', 'a', journal))
        r.register(AgentSpec(id='final', name='Final', description='…',
                             consumes=('amont',), produces='final',
                             entrypoint='autre_methode'), loader=lambda: None)
        with pytest.raises(NotExecutable):
            Executor(r).execute(Planner(r).plan('final'), _contexte())
        assert journal == []


class TestEchecs:
    def test_une_panne_conserve_le_format_d_erreur_historique(self):
        """`core/orchestrator.py` lève « [Nom] Erreur critique : … ». Changer ce
        format modifierait ce que voient les appelants."""
        registre = _registre_chaine(casse=('amont',))
        with pytest.raises(ExecutionError, match=r'\[Amont\] Erreur critique : panne simulée'):
            Executor(registre).execute(Planner(registre).plan('aval'), _contexte())

    def test_une_panne_est_consignee_dans_le_contexte(self):
        registre = _registre_chaine(casse=('amont',))
        ctx = _contexte()
        with pytest.raises(ExecutionError):
            Executor(registre).execute(Planner(registre).plan('aval'), ctx)
        assert ctx._errors == [{'agent': 'amont', 'error': 'panne simulée de amont'}]

    def test_une_panne_en_amont_empeche_l_aval_de_tourner(self):
        """Laisser l'aval s'exécuter produirait une stratégie sans matière."""
        journal = []
        registre = _registre_chaine(journal, casse=('amont',))
        with pytest.raises(ExecutionError):
            Executor(registre).execute(Planner(registre).plan('aval'), _contexte())
        assert journal == ['amont']


class TestTrace:
    def test_la_trace_dit_ce_qui_s_est_passe(self):
        registre = _registre_chaine()
        _, trace = Executor(registre).execute(Planner(registre).plan('aval'), _contexte())
        assert [s.agent_id for s in trace.steps] == ['amont', 'aval']
        assert all(s.status == STEP_OK for s in trace.steps)
        assert trace.ok and not trace.degraded

    def test_un_resultat_degrade_est_signale_comme_tel(self):
        """Le distinguer d'un résultat complet évite d'annoncer une qualité qui
        n'est pas là."""
        r = AgentRegistry()
        r.register(AgentSpec(id='seul', name='Seul', description='…',
                             consumes=('comments', 'contexte_riche'),
                             optional_consumes=('contexte_riche',),
                             produces='seul'),
                   loader=lambda: _agent_factice('seul', 'x'))
        _, trace = Executor(r).execute(Planner(r).plan('seul'), _contexte())
        assert trace.ok is True
        assert trace.degraded is True
        assert trace.steps[0].degraded_without == ('contexte_riche',)

    def test_la_trace_est_serialisable_et_lisible(self):
        registre = _registre_chaine()
        _, trace = Executor(registre).execute(Planner(registre).plan('aval'), _contexte())
        d = trace.describe()
        assert d['ok'] is True and len(d['steps']) == 2
        assert 'Amont' in Executor(registre).explain(trace)


class TestParallelisme:
    def _registre_en_y(self, journal):
        r = AgentRegistry()
        for aid in ('gauche', 'droite'):
            r.register(AgentSpec(id=aid, name=aid.title(), description='…',
                                 consumes=('comments',), produces=f'{aid}_out'),
                       loader=(lambda a: lambda: _agent_factice(a, a, journal))(aid))
        r.register(AgentSpec(id='synthese', name='Synthèse', description='…',
                             consumes=('gauche_out', 'droite_out'),
                             produces='synthese'),
                   loader=lambda: _agent_factice('synthese', 's', journal))
        return r

    def test_une_vague_parallele_execute_tout_avant_la_suivante(self):
        """La synthèse ne doit jamais démarrer avant ses deux sources."""
        journal = []
        registre = self._registre_en_y(journal)
        ctx, trace = Executor(registre).execute(
            Planner(registre).plan('synthese'), _contexte(), parallel=True)
        assert set(journal[:2]) == {'gauche', 'droite'}
        assert journal[2] == 'synthese'
        assert trace.ok and len(trace.steps) == 3

    def test_le_mode_sequentiel_donne_le_meme_resultat(self):
        """Paralléliser ne doit rien changer au contenu produit."""
        registre = self._registre_en_y([])
        plan = Planner(registre).plan('synthese')
        ctx_s, _ = Executor(registre).execute(plan, _contexte())
        ctx_p, _ = Executor(registre).execute(plan, _contexte(), parallel=True)
        assert ctx_s.to_response() == ctx_p.to_response()


class TestGainReelDuParallelisme:
    """Mesure demandée par le brief : temps séquentiel, temps parallèle, gain
    réel — pas seulement « l'ordre est correct ».

    Nuance importante : aucune mission actuelle de Gabriel n'a de branches
    indépendantes (Psychologue → Stratège → Créateur est une chaîne). Ce gain
    est donc *disponible mais inutilisé*. Le mesurer répond à la vraie
    question : le jour où une mission aura deux branches, la parallélisation
    apportera-t-elle quelque chose ?
    """

    LATENCE = 0.2   # simule une étape qui attend un appel réseau ou LLM

    def _registre_en_y(self, n_branches):
        import time as _time
        from agents.registry import AgentRegistry, AgentSpec

        latence = self.LATENCE

        def _agent(agent_id):
            class _A:
                AGENT_ID = agent_id

                def run(self, ctx):
                    _time.sleep(latence)
                    ctx.add(agent_id, {f'{agent_id}_out': True})
                    return ctx
            return _A

        r = AgentRegistry()
        branches = [f'branche{i}' for i in range(n_branches)]
        for b in branches:
            r.register(AgentSpec(id=b, name=b, description='…',
                                 consumes=('comments',), produces=f'{b}_out'),
                       loader=(lambda x: lambda: _agent(x))(b))
        r.register(AgentSpec(id='synthese', name='Synthèse', description='…',
                             consumes=tuple(f'{b}_out' for b in branches),
                             produces='synthese'),
                   loader=lambda: _agent('synthese'))
        return r

    def _mesurer(self, n_branches):
        import time as _time
        from core.planner import Planner

        registre = self._registre_en_y(n_branches)
        plan = Planner(registre).plan('synthese')

        def _ctx():
            return AnalysisContext(comments=['a'], brain_context='',
                                   video_context='', title='')

        debut = _time.perf_counter()
        Executor(registre).execute(plan, _ctx())
        sequentiel = _time.perf_counter() - debut

        debut = _time.perf_counter()
        Executor(registre).execute(plan, _ctx(), parallel=True)
        parallele = _time.perf_counter() - debut

        return sequentiel, parallele

    def test_le_parallelisme_apporte_un_gain_mesurable(self):
        """Trois branches indépendantes + une synthèse : en séquentiel, quatre
        latences ; en parallèle, deux. Le seuil est volontairement lâche —
        c'est le gain qu'on vérifie, pas une performance au centième."""
        sequentiel, parallele = self._mesurer(3)
        assert parallele < sequentiel * 0.75, (
            f"aucun gain mesurable : {sequentiel:.2f}s séquentiel contre "
            f"{parallele:.2f}s parallèle")

    def test_le_gain_grandit_avec_le_nombre_de_branches(self):
        """Propriété qui distingue un vrai parallélisme d'un gain accidentel :
        cinq branches doivent en profiter plus que deux."""
        seq2, par2 = self._mesurer(2)
        seq5, par5 = self._mesurer(5)
        assert (seq5 / par5) > (seq2 / par2)

    def test_le_temps_parallele_ne_depend_pas_du_nombre_de_branches(self):
        """La signature d'une vraie exécution simultanée : ajouter des
        branches n'allonge pas la vague. Si ce test échoue, la
        parallélisation s'est mise à sérialiser sans le dire."""
        _, par2 = self._mesurer(2)
        _, par5 = self._mesurer(5)
        assert par5 < par2 * 1.6, (
            f"passer de 2 à 5 branches a allongé la vague : "
            f"{par2:.2f}s → {par5:.2f}s")
