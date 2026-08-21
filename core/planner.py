"""Planificateur d'exécution.

Les trois registres déclarent ce que Gabriel sait faire. Ce module est le
premier à s'en servir pour *décider* : à partir d'un objectif, il construit
l'ordre dans lequel les agents doivent tourner.

Ce qu'il remplace. Aujourd'hui, `core/orchestrator.py` contient deux pipelines
écrits en dur, et la dépendance du Stratège envers le Psychologue n'est qu'une
convention d'appel : rien ne l'impose. Appeler `run_stratege` sans données
psychologiques ne lève aucune erreur — cela produit une stratégie sans matière.
Le plan rend cette dépendance explicite et vérifiable avant de lancer quoi que
ce soit de long ou de facturé.

Ce qu'il n'est pas. Il ne remplace pas l'orchestrateur : celui-ci *exécute*,
le planificateur *ordonne*. Et il ne fait appel à aucun modèle — l'ordre se
déduit des dépendances déclarées. Confier à un LLM un calcul déterministe
introduirait du coût, de la latence et de l'imprévisibilité pour un résultat
qu'un tri topologique donne exactement.
"""

from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Tuple


class PlanError(Exception):
    """Impossible de construire un plan."""


class UnreachableGoal(PlanError):
    """L'objectif ne peut pas être atteint avec les agents disponibles."""


class CircularDependency(PlanError):
    """Les dépendances déclarées forment un cycle."""


@dataclass(frozen=True)
class PlanStep:
    """Une étape du plan : quel agent, comment l'appeler, ce qu'il attend."""

    agent_id: str
    agent_name: str
    entrypoint: str
    produces: str
    depends_on: Tuple[str, ...] = ()      # étapes qui doivent précéder
    external_inputs: Tuple[str, ...] = () # ce que l'appelant doit fournir
    # Ce dont l'étape peut se passer, au prix de la qualité. Le distinguer
    # évite deux erreurs symétriques : bloquer un parcours qui fonctionne, et
    # annoncer un résultat complet alors qu'il a tourné à vide.
    degraded_without: Tuple[str, ...] = ()

    # Ce que l'étape mobilisera réellement, lu sur la fiche de l'agent. Sans
    # ces deux champs, un plan répond « quel agent » mais jamais « avec quels
    # instruments et quelle méthode » — or c'est cela qui distingue une
    # composition assumée d'un enchaînement deviné.
    tools: Tuple[str, ...] = ()
    skills: Tuple[str, ...] = ()
    wave: int = 0                         # étapes de même vague : parallélisables

    def describe(self) -> dict:
        return {
            'agent_id': self.agent_id,
            'agent_name': self.agent_name,
            'entrypoint': self.entrypoint,
            'produces': self.produces,
            'depends_on': list(self.depends_on),
            'external_inputs': list(self.external_inputs),
            'degraded_without': list(self.degraded_without),
            'tools': list(self.tools),
            'skills': list(self.skills),
            'wave': self.wave,
        }


@dataclass(frozen=True)
class ExecutionPlan:
    """Le plan : des étapes ordonnées, et ce qu'il faut fournir pour l'exécuter."""

    goal: str
    steps: Tuple[PlanStep, ...]
    required_inputs: Tuple[str, ...] = ()   # sans quoi le plan ne peut pas tourner
    optional_inputs: Tuple[str, ...] = ()   # améliorent le résultat, sans bloquer
    already_available: Tuple[str, ...] = ()

    @property
    def agent_ids(self) -> Tuple[str, ...]:
        return tuple(step.agent_id for step in self.steps)

    def waves(self) -> Tuple[Tuple[PlanStep, ...], ...]:
        """Les étapes regroupées par vague. Une vague peut tourner en parallèle.

        Sans ce regroupement, tout plan s'exécuterait en série — y compris deux
        analyses qui ne dépendent l'une de l'autre en rien.
        """
        if not self.steps:
            return ()
        largeur = max(step.wave for step in self.steps) + 1
        groupes: List[List[PlanStep]] = [[] for _ in range(largeur)]
        for step in self.steps:
            groupes[step.wave].append(step)
        return tuple(tuple(g) for g in groupes if g)

    @property
    def parallelizable(self) -> bool:
        return any(len(v) > 1 for v in self.waves())

    @property
    def tools(self) -> Tuple[str, ...]:
        """Tous les outils que ce plan mobilisera, sans doublon."""
        vus = []
        for step in self.steps:
            for tool_id in step.tools:
                if tool_id not in vus:
                    vus.append(tool_id)
        return tuple(vus)

    @property
    def skills(self) -> Tuple[str, ...]:
        """Tous les savoir-faire que ce plan mobilisera, sans doublon."""
        vus = []
        for step in self.steps:
            for skill_id in step.skills:
                if skill_id not in vus:
                    vus.append(skill_id)
        return tuple(vus)

    def describe(self) -> dict:
        return {
            'goal': self.goal,
            'steps': [s.describe() for s in self.steps],
            'required_inputs': list(self.required_inputs),
            'optional_inputs': list(self.optional_inputs),
            'already_available': list(self.already_available),
            'waves': [[s.agent_id for s in v] for v in self.waves()],
            'parallelizable': self.parallelizable,
            'tools': list(self.tools),
            'skills': list(self.skills),
        }

    def __len__(self) -> int:
        return len(self.steps)

    def __iter__(self):
        return iter(self.steps)


class Planner:
    """Construit un plan d'exécution à partir des agents déclarés."""

    def __init__(self, agent_registry) -> None:
        self._agents = agent_registry

    # ── Lecture du registre ──────────────────────────────────────────────────

    def _producers(self) -> Dict[str, str]:
        """Qui produit quoi. Un besoin sans producteur est une entrée externe."""
        return {a.spec.produces: a.spec.id
                for a in self._agents.available() if a.spec.produces}

    # ── Construction ─────────────────────────────────────────────────────────

    def plan(self, goal: str, available: Iterable[str] = ()) -> ExecutionPlan:
        """Ordonne les agents nécessaires pour atteindre `goal`.

        `available` liste ce qui est déjà en main — par exemple un rapport
        psychologique produit lors d'une session précédente. Une dépendance
        déjà satisfaite n'est pas rejouée : c'est ce qui permet au plan de
        décrire aussi bien une chaîne complète qu'une reprise en cours de route.
        """
        deja = tuple(dict.fromkeys(available))
        cible = self._agents.get(goal)   # lève AgentNotFound si inconnu
        if not cible.spec.usable:
            raise UnreachableGoal(
                f"L'objectif « {goal} » vise l'agent {cible.spec.name}, qui "
                f"n'est pas utilisable (statut : {cible.spec.status}).")

        producteurs = self._producers()
        ordre: List[str] = []
        externes: List[str] = []
        externes_souples: List[str] = []
        profondeurs: Dict[str, int] = {}
        deps_par_agent: Dict[str, Tuple[str, ...]] = {}
        externes_par_agent: Dict[str, Tuple[str, ...]] = {}
        souples_par_agent: Dict[str, Tuple[str, ...]] = {}

        def visiter(agent_id: str, chemin: Tuple[str, ...]) -> int:
            if agent_id in chemin:
                boucle = ' → '.join(chemin[chemin.index(agent_id):] + (agent_id,))
                raise CircularDependency(
                    f"Dépendances circulaires entre agents : {boucle}.")
            if agent_id in profondeurs:
                return profondeurs[agent_id]

            spec = self._agents.spec(agent_id)
            deps: List[str] = []
            manquants: List[str] = []
            souples: List[str] = []
            profondeur = 0

            for besoin in spec.consumes:
                if besoin in deja:
                    continue                      # déjà en main : on ne rejoue pas
                facultatif = besoin in spec.optional_consumes
                if facultatif:
                    souples.append(besoin)
                fournisseur = producteurs.get(besoin)
                if fournisseur is None:
                    manquants.append(besoin)      # entrée externe : à fournir
                    cible_liste = externes_souples if facultatif else externes
                    if besoin not in cible_liste:
                        cible_liste.append(besoin)
                    continue
                profondeur = max(profondeur, visiter(fournisseur, chemin + (agent_id,)) + 1)
                deps.append(fournisseur)

            profondeurs[agent_id] = profondeur
            deps_par_agent[agent_id] = tuple(deps)
            externes_par_agent[agent_id] = tuple(manquants)
            souples_par_agent[agent_id] = tuple(souples)
            if agent_id not in ordre:
                ordre.append(agent_id)
            return profondeur

        visiter(goal, ())

        # Tri par profondeur : garantit qu'une dépendance précède toujours ce
        # qui l'utilise, et regroupe ce qui peut tourner ensemble.
        ordre.sort(key=lambda a: (profondeurs[a], a))
        steps = tuple(
            PlanStep(
                agent_id=aid,
                agent_name=self._agents.spec(aid).name,
                entrypoint=self._agents.spec(aid).entrypoint,
                produces=self._agents.spec(aid).produces,
                depends_on=deps_par_agent[aid],
                external_inputs=externes_par_agent[aid],
                degraded_without=souples_par_agent[aid],
                tools=self._agents.spec(aid).tools,
                skills=self._agents.spec(aid).skills,
                wave=profondeurs[aid],
            )
            for aid in ordre
        )
        return ExecutionPlan(goal=goal, steps=steps,
                             required_inputs=tuple(externes),
                             optional_inputs=tuple(externes_souples),
                             already_available=deja)

    def explain(self, goal: str, available: Iterable[str] = ()) -> str:
        """Le plan en clair — pour un journal d'exécution ou un rapport."""
        plan = self.plan(goal, available)
        lignes = [f"Objectif : {goal}"]
        if plan.already_available:
            lignes.append(f"Déjà en main : {', '.join(plan.already_available)}")
        if plan.required_inputs:
            lignes.append(f"À fournir : {', '.join(plan.required_inputs)}")
        if plan.optional_inputs:
            lignes.append(f"Facultatif (qualité moindre sans) : "
                          f"{', '.join(plan.optional_inputs)}")
        for index, vague in enumerate(plan.waves(), start=1):
            noms = ', '.join(s.agent_name for s in vague)
            marque = ' (en parallèle)' if len(vague) > 1 else ''
            lignes.append(f"  {index}. {noms}{marque}")
            # Dire ce que chaque étape mobilise : c'est la différence entre
            # « appelle cet agent » et « appelle cet agent, avec ces
            # instruments et cette méthode ».
            for step in vague:
                if step.tools:
                    lignes.append(f"     outils : {', '.join(step.tools)}")
                if step.skills:
                    lignes.append(f"     méthodes : {', '.join(step.skills)}")
        return '\n'.join(lignes)


def default_planner() -> Planner:
    from agents.catalog import registry
    return Planner(registry)
