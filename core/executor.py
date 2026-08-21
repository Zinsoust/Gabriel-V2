"""Exécution d'un plan.

Le planificateur ordonne, cet module déroule. C'est la pièce qui transforme
les registres en comportement : jusqu'ici, le catalogue décrivait Gabriel sans
que rien ne s'en serve pour agir.

Ce qu'il apporte par rapport aux pipelines écrits en dur de
``core/orchestrator.py`` :

* **Il vérifie avant de lancer.** Un plan dont les entrées indispensables
  manquent est refusé tout de suite, au lieu de partir sur une analyse longue
  et facturée qui échouera plus loin — ou pire, qui rendra un résultat creux.
* **Il laisse une trace.** Chaque étape consigne son issue et sa durée. Le code
  actuel imprime des lignes dans la console et n'en garde rien.
* **Il nomme le mode dégradé.** Une dépendance souple absente n'arrête pas
  l'exécution, mais elle est inscrite dans la trace — de quoi dire à
  l'utilisateur que le résultat a tourné sans toute la matière.

Ce qu'il ne fait pas : il ne remplace pas l'orchestrateur et ne connaît aucun
agent en particulier. Il applique un plan, quel qu'il soit.
"""

import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Optional, Tuple

from core.planner import ExecutionPlan, PlanStep


class ExecutionError(RuntimeError):
    """L'exécution d'un plan a échoué."""


class MissingInputs(ExecutionError):
    """Le plan ne peut pas démarrer : des entrées indispensables manquent."""


class NotExecutable(ExecutionError):
    """Une étape ne suit pas le protocole d'exécution."""


# Issues possibles d'une étape.
STEP_OK = 'ok'
STEP_FAILED = 'failed'
STEP_SKIPPED = 'skipped'


@dataclass(frozen=True)
class StepResult:
    agent_id: str
    agent_name: str
    status: str
    duration_ms: int = 0
    error: str = ''
    degraded_without: Tuple[str, ...] = ()

    @property
    def ok(self) -> bool:
        return self.status == STEP_OK

    @property
    def degraded(self) -> bool:
        return self.ok and bool(self.degraded_without)

    def describe(self) -> dict:
        return {
            'agent_id': self.agent_id,
            'agent_name': self.agent_name,
            'status': self.status,
            'duration_ms': self.duration_ms,
            'error': self.error,
            'degraded_without': list(self.degraded_without),
        }


@dataclass
class ExecutionTrace:
    """Ce qui s'est réellement passé — la matière d'un journal d'exécution."""

    goal: str
    steps: list = field(default_factory=list)
    # Ce que la réunion des contributions a coûté. Renseigné en fin
    # d'exécution : un agent dont le résultat a été écrasé par un autre doit
    # apparaître dans la trace, pas disparaître en silence.
    synthesis: object = None

    @property
    def ok(self) -> bool:
        return all(s.ok for s in self.steps)

    @property
    def lossless(self) -> bool:
        """Aucune contribution d'agent n'a été perdue à la réunion."""
        return self.synthesis is None or self.synthesis.lossless

    @property
    def degraded(self) -> bool:
        return any(s.degraded for s in self.steps)

    @property
    def duration_ms(self) -> int:
        return sum(s.duration_ms for s in self.steps)

    def describe(self) -> dict:
        return {
            'goal': self.goal,
            'ok': self.ok,
            'degraded': self.degraded,
            'duration_ms': self.duration_ms,
            'lossless': self.lossless,
            'steps': [s.describe() for s in self.steps],
            'synthesis': self.synthesis.describe() if self.synthesis else None,
        }


class Executor:
    """Déroule un plan sur un contexte d'analyse."""

    def __init__(self, agent_registry=None) -> None:
        if agent_registry is None:
            from agents.catalog import registry as agent_registry
        self._agents = agent_registry

    # ── Vérifications préalables ─────────────────────────────────────────────

    def check(self, plan: ExecutionPlan, ctx) -> None:
        """Refuse un plan qui ne peut pas aboutir, avant toute dépense.

        Une entrée indispensable absente ne produit pas une erreur franche plus
        loin : elle produit un résultat vide qui ressemble à un résultat.
        """
        manquantes = [nom for nom in plan.required_inputs
                      if not getattr(ctx, nom, None)]
        if manquantes:
            raise MissingInputs(
                f"Le plan « {plan.goal} » ne peut pas démarrer : "
                f"{', '.join(manquantes)} manquant(s) dans le contexte.")

        for step in plan.steps:
            if step.entrypoint != 'run':
                raise NotExecutable(
                    f"L'étape « {step.agent_id} » s'appelle "
                    f"« {step.entrypoint} » et ne suit pas le protocole "
                    f"run(ctx) : elle ne peut pas être exécutée par un plan.")

    # ── Exécution ────────────────────────────────────────────────────────────

    def _run_step(self, step: PlanStep, ctx) -> StepResult:
        agent = self._agents.resolve(step.agent_id)()
        depart = time.perf_counter()
        try:
            agent.run(ctx)
        except Exception as error:
            duree = int((time.perf_counter() - depart) * 1000)
            ctx.record_error(step.agent_id, str(error))
            # Format conservé à l'identique de core/orchestrator.py : c'est ce
            # que les appelants voient aujourd'hui.
            raise ExecutionError(
                f"[{step.agent_name}] Erreur critique : {error}") from error
        duree = int((time.perf_counter() - depart) * 1000)
        return StepResult(step.agent_id, step.agent_name, STEP_OK, duree,
                          degraded_without=step.degraded_without)

    def execute(self, plan: ExecutionPlan, ctx, *, parallel: bool = False):
        """Déroule le plan et renvoie ``(ctx, trace)``.

        ``parallel`` autorise les étapes d'une même vague à tourner ensemble.
        Laissé à False par défaut : les plans actuels de Gabriel sont des
        chaînes linéaires, et les agents ouvrent déjà leurs propres pools de
        tâches — paralléliser sans besoin ne ferait qu'ajouter du risque.
        """
        self.check(plan, ctx)
        trace = ExecutionTrace(goal=plan.goal)

        for vague in plan.waves():
            if parallel and len(vague) > 1:
                with ThreadPoolExecutor(max_workers=len(vague)) as pool:
                    resultats = list(pool.map(lambda s: self._run_step(s, ctx), vague))
            else:
                resultats = [self._run_step(step, ctx) for step in vague]
            trace.steps.extend(resultats)

        # Réunion des contributions : la réponse ne change pas, mais ce
        # qu'elle écrase devient visible dans la trace.
        from core.synthesis import synthesize
        trace.synthesis = synthesize(ctx)

        return ctx, trace

    def explain(self, trace: ExecutionTrace) -> str:
        """La trace en clair — pour un compte rendu lisible."""
        lignes = [f"Objectif : {trace.goal} — "
                  f"{'terminé' if trace.ok else 'échoué'}"
                  f"{' (dégradé)' if trace.degraded else ''}"]
        if trace.synthesis is not None and not trace.lossless:
            for collision in trace.synthesis.collisions:
                perdus = ', '.join(collision.overwritten_from)
                lignes.append(
                    f"  ⚠ « {collision.key} » : contribution de {perdus} "
                    f"écrasée par {collision.kept_from}")
        for step in trace.steps:
            detail = f"{step.duration_ms} ms"
            if step.degraded_without:
                detail += f", sans {', '.join(step.degraded_without)}"
            lignes.append(f"  - {step.agent_name} : {step.status} ({detail})")
        return '\n'.join(lignes)
