"""Synthèse — dernière étape du schéma d'architecture.

Sa règle fondatrice : la réponse rendue ne doit pas changer. `to_response()`
est ce que le code de production consomme ; la synthèse décrit cette même
réponse, elle ne la corrige pas. Un module qui « améliorerait » la fusion en
douce changerait le produit sans que personne l'ait décidé.
"""

import pytest

from agents.context import AnalysisContext
from core.synthesis import Synthesis, synthesize


def _ctx(**contributions):
    ctx = AnalysisContext(comments=[], brain_context='', video_context='', title='')
    for agent_id, data in contributions.items():
        ctx.add(agent_id, data)
    return ctx


class TestLaReponseRendueNeChangePas:
    """La garantie la plus importante : la synthèse observe, elle ne corrige
    pas. Le jour où elle divergerait de `to_response`, du code de production
    recevrait autre chose que ce que ces tests décrivent."""

    def test_sans_collision_la_reponse_est_identique(self):
        ctx = _ctx(psychologue={'kpis': {'e': 72}}, stratege={'strategie': {'d': 'X'}})
        assert synthesize(ctx).response == ctx.to_response()

    def test_avec_collision_la_reponse_reste_identique(self):
        """Y compris quand une contribution est perdue : la synthèse signale
        la perte, elle ne la répare pas."""
        ctx = _ctx(psychologue={'brief': 'A'}, stratege={'brief': 'B'})
        synthese = synthesize(ctx)
        assert synthese.response == ctx.to_response()
        assert synthese.response['brief'] == 'B'   # dernier écrit, comme avant

    def test_un_contexte_vide_rend_une_reponse_vide(self):
        ctx = _ctx()
        assert synthesize(ctx).response == ctx.to_response() == {}


class TestLaPerteDevientVisible:
    """Le défaut corrigé : `result.update(data)` fait disparaître une
    contribution sans erreur, sans avertissement, sans trace."""

    def test_une_collision_est_signalee_avec_ses_deux_cotes(self):
        synthese = synthesize(_ctx(psychologue={'brief': 'A'}, stratege={'brief': 'B'}))
        assert synthese.lossless is False
        assert len(synthese.collisions) == 1
        collision = synthese.collisions[0]
        assert collision.key == 'brief'
        assert collision.kept_from == 'stratege'
        assert collision.overwritten_from == ('psychologue',)

    def test_sans_collision_la_synthese_se_declare_sans_perte(self):
        synthese = synthesize(_ctx(psychologue={'kpis': 1}, stratege={'strategie': 2}))
        assert synthese.lossless is True
        assert synthese.collisions == ()

    def test_trois_agents_sur_la_meme_cle_nomment_les_deux_perdants(self):
        """Un écrasement en cascade ne doit pas n'en signaler qu'un seul."""
        synthese = synthesize(_ctx(psychologue={'x': 1}, stratege={'x': 2}, createur={'x': 3}))
        collision = synthese.collisions[0]
        assert collision.kept_from == 'createur'
        assert collision.overwritten_from == ('psychologue', 'stratege')

    def test_la_perte_est_lisible_en_clair(self):
        texte = synthesize(_ctx(psychologue={'brief': 'A'}, stratege={'brief': 'B'})).explain()
        assert 'brief' in texte and 'psychologue' in texte and 'stratege' in texte


class TestProvenance:
    def test_chaque_cle_sait_de_quel_agent_elle_vient(self):
        """Aujourd'hui la réponse est un dictionnaire plat : impossible de
        savoir qui a produit quoi une fois fusionné."""
        synthese = synthesize(_ctx(psychologue={'kpis': 1}, stratege={'strategie': 2}))
        assert synthese.provenance == {'kpis': 'psychologue', 'strategie': 'stratege'}

    def test_les_contributeurs_sont_listes_dans_l_ordre_d_execution(self):
        synthese = synthesize(_ctx(psychologue={'a': 1}, stratege={'b': 2}))
        assert synthese.contributors == ('psychologue', 'stratege')

    def test_une_contribution_non_dictionnaire_est_ignoree_comme_avant(self):
        """`to_response` saute les valeurs non-dict ; la synthèse doit faire
        exactement pareil, sinon elle décrirait une autre réponse."""
        ctx = _ctx(psychologue={'a': 1})
        ctx.add('bizarre', 'une chaîne, pas un dict')
        synthese = synthesize(ctx)
        assert synthese.response == ctx.to_response()
        assert 'bizarre' not in synthese.contributors


class TestPipelineReel:
    def test_la_synthese_decrit_le_vrai_pipeline_du_psychologue(self, monkeypatch):
        import core.analyzer as analyzer
        from core.orchestrator import Gabriel

        monkeypatch.setattr(analyzer, 'call_llm', lambda *a, **k: '{"placeholder": true}')
        monkeypatch.setattr(analyzer, '_NLP_AVAILABLE', False)

        gabriel = Gabriel()
        reponse = gabriel.run_psycho(
            [{'text': 'Merci beaucoup', 'likes': 5},
             {'text': 'Pas convaincu', 'likes': 2}], title='Test')

        # Un seul agent : aucune collision possible.
        assert set(reponse) and isinstance(reponse, dict)
        assert len(reponse) > 5   # le Psychologue produit une dizaine de clés


class TestLaTraceDExecutionSignaleLaPerte:
    """Brancher la synthèse dans l'Executor donne à un plan la même honnêteté
    que le reste de la couche : ce qui est perdu apparaît dans la trace."""

    def _registre_en_collision(self):
        from agents.registry import AgentRegistry, AgentSpec

        def _agent(agent_id, cle, valeur):
            class _Factice:
                AGENT_ID = agent_id

                def run(self, ctx):
                    ctx.add(agent_id, {cle: valeur})
                    return ctx
            return _Factice

        r = AgentRegistry()
        r.register(AgentSpec(id='amont', name='Amont', description='…',
                             consumes=('comments',), produces='amont'),
                   loader=lambda: _agent('amont', 'rapport', 'valeur amont'))
        r.register(AgentSpec(id='aval', name='Aval', description='…',
                             consumes=('amont',), produces='aval'),
                   loader=lambda: _agent('aval', 'rapport', 'valeur aval'))
        return r

    def test_une_contribution_ecrasee_apparait_dans_la_trace(self):
        from core.executor import Executor
        from core.planner import Planner

        registre = self._registre_en_collision()
        ctx = AnalysisContext(comments=['a'], brain_context='',
                              video_context='', title='')
        ctx, trace = Executor(registre).execute(Planner(registre).plan('aval'), ctx)

        assert trace.ok is True          # l'exécution a réussi…
        assert trace.lossless is False   # …mais une contribution a disparu
        assert trace.synthesis.collisions[0].key == 'rapport'
        assert 'écrasée' in Executor(registre).explain(trace)

    def test_une_execution_sans_collision_se_declare_sans_perte(self):
        from agents.registry import AgentRegistry, AgentSpec
        from core.executor import Executor
        from core.planner import Planner

        class _Seul:
            AGENT_ID = 'seul'

            def run(self, ctx):
                ctx.add('seul', {'resultat': 1})
                return ctx

        r = AgentRegistry()
        r.register(AgentSpec(id='seul', name='Seul', description='…',
                             consumes=('comments',), produces='seul'),
                   loader=lambda: _Seul)
        ctx = AnalysisContext(comments=['a'], brain_context='',
                              video_context='', title='')
        _, trace = Executor(r).execute(Planner(r).plan('seul'), ctx)

        assert trace.lossless is True
        assert trace.describe()['synthesis']['lossless'] is True
