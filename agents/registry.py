"""Registre des agents Gabriel.

Troisième couche du Core, celle qui referme la boucle : un Tool *fait*, un
Skill *enseigne comment*, un Agent *décide de quoi mobiliser*. Le registre
déclare, pour chaque agent, ce qu'il consomme, ce qu'il produit, les outils
qu'il a le droit d'employer et les savoir-faire dont il se sert.

Ce qu'il apporte que `agents/__init__.py` n'apportait pas :

* **La vérité sur les points d'entrée.** Les quatre agents y sont présentés
  comme interchangeables alors que `Createur.run()` et `Architecte.run()`
  lèvent une exception. Le registre déclare le vrai point d'entrée et le vrai
  statut de chacun.
* **Une cohérence vérifiée entre les trois couches.** Un agent qui déclare un
  outil ou un savoir-faire inexistant est refusé à l'enregistrement, au
  démarrage, plutôt que de casser en production au moment de s'en servir.
* **L'accès direct rendu explicite.** Chaque agent doit rester joignable seul,
  sans passer par une orchestration. C'est une contrainte produit ; elle est
  désormais déclarée et testable, au lieu d'être une habitude.
"""

from dataclasses import dataclass, field
from typing import Callable, Dict, Optional, Tuple


class AgentError(Exception):
    """Erreur de la couche Agent."""


class AgentNotFound(AgentError, KeyError):
    """Aucun agent sous cet identifiant."""


class AgentUnavailable(AgentError):
    """L'agent est déclaré mais n'est pas utilisable en l'état."""


# Statuts possibles d'un agent, du plus utilisable au moins utilisable.
STATUS_AVAILABLE = 'available'      # utilisable en production
STATUS_PLANNED = 'planned'          # déclaré, pas encore implémenté
STATUS_UNAVAILABLE = 'unavailable'  # devrait marcher, mais n'a pas pu charger

_STATUSES = (STATUS_AVAILABLE, STATUS_PLANNED, STATUS_UNAVAILABLE)


@dataclass(frozen=True)
class AgentSpec:
    """Fiche d'identité d'un agent, lisible par le Core."""

    id: str
    name: str
    description: str

    # Le vrai point d'entrée. `run` pour les agents du pipeline ; une fonction
    # nommée pour ceux qui n'ont jamais eu de `run` utilisable.
    entrypoint: str = 'run'
    status: str = STATUS_AVAILABLE

    # Ce dont l'agent a besoin dans le contexte, et ce qu'il y dépose.
    consumes: Tuple[str, ...] = ()
    produces: str = ''

    # Ce qu'il mobilise. Vérifié contre les registres à l'enregistrement.
    tools: Tuple[str, ...] = ()
    skills: Tuple[str, ...] = ()

    # Contrainte produit : chaque agent reste joignable seul.
    direct_access: bool = True
    route: str = ''

    def __post_init__(self):
        if self.status not in _STATUSES:
            raise ValueError(
                f"Statut invalide pour « {self.id} » : {self.status!r}. "
                f"Attendu : {', '.join(_STATUSES)}.")

    @property
    def usable(self) -> bool:
        return self.status == STATUS_AVAILABLE

    def describe(self) -> dict:
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'entrypoint': self.entrypoint,
            'status': self.status,
            'usable': self.usable,
            'consumes': list(self.consumes),
            'produces': self.produces,
            'tools': list(self.tools),
            'skills': list(self.skills),
            'direct_access': self.direct_access,
            'route': self.route,
        }


@dataclass
class RegisteredAgent:
    """Un agent déclaré, et de quoi l'atteindre."""

    spec: AgentSpec
    loader: Optional[Callable[[], object]] = None

    def resolve(self):
        """Charge la classe de l'agent. Levée explicite si indisponible."""
        if self.loader is None:
            raise AgentUnavailable(
                f"L'agent « {self.spec.id} » est déclaré sans implémentation "
                f"joignable (statut : {self.spec.status}).")
        return self.loader()

    def describe(self) -> dict:
        return self.spec.describe()


class AgentRegistry:
    def __init__(self, tool_registry=None, skill_registry=None) -> None:
        self._agents: Dict[str, RegisteredAgent] = {}
        self._tools = tool_registry
        self._skills = skill_registry

    # ── Cohérence entre couches ──────────────────────────────────────────────

    def _check_capabilities(self, spec: AgentSpec) -> None:
        """Refuse une déclaration qui référence une capacité inexistante.

        Sans cette vérification, une faute de frappe dans un identifiant
        d'outil ne se manifesterait qu'au moment de l'appel — c'est-à-dire en
        production, au milieu d'une analyse payée par l'utilisateur.
        """
        if self._tools is not None:
            for tool_id in spec.tools:
                if tool_id not in self._tools:
                    raise ValueError(
                        f"L'agent « {spec.id} » déclare l'outil inconnu "
                        f"« {tool_id} ».")
                autorises = self._tools.get(tool_id).spec.allowed_agents
                if autorises and spec.id not in autorises:
                    raise ValueError(
                        f"L'agent « {spec.id} » déclare l'outil « {tool_id} », "
                        f"qui ne l'autorise pas (autorisés : "
                        f"{', '.join(autorises)}).")
        if self._skills is not None:
            for skill_id in spec.skills:
                if skill_id not in self._skills:
                    raise ValueError(
                        f"L'agent « {spec.id} » déclare le savoir-faire "
                        f"inconnu « {skill_id} ».")

    # ── Enregistrement et lecture ────────────────────────────────────────────

    def register(self, spec: AgentSpec, loader=None) -> RegisteredAgent:
        if spec.id in self._agents:
            raise ValueError(
                f"Agent « {spec.id} » déjà enregistré : deux implémentations "
                f"sous un même identifiant se masqueraient silencieusement.")
        self._check_capabilities(spec)
        entry = RegisteredAgent(spec=spec, loader=loader)
        self._agents[spec.id] = entry
        return entry

    def get(self, agent_id: str) -> RegisteredAgent:
        try:
            return self._agents[agent_id]
        except KeyError:
            connus = ', '.join(sorted(self._agents)) or '(aucun)'
            raise AgentNotFound(
                f"Agent inconnu : « {agent_id} ». Agents déclarés : {connus}."
            ) from None

    def spec(self, agent_id: str) -> AgentSpec:
        return self.get(agent_id).spec

    def resolve(self, agent_id: str):
        """Charge un agent utilisable. Refuse explicitement les autres."""
        entry = self.get(agent_id)
        if not entry.spec.usable:
            raise AgentUnavailable(
                f"L'agent « {agent_id} » n'est pas utilisable "
                f"(statut : {entry.spec.status}).")
        return entry.resolve()

    def all(self) -> Tuple[RegisteredAgent, ...]:
        return tuple(self._agents[k] for k in sorted(self._agents))

    def available(self) -> Tuple[RegisteredAgent, ...]:
        return tuple(a for a in self.all() if a.spec.usable)

    def with_direct_access(self) -> Tuple[RegisteredAgent, ...]:
        return tuple(a for a in self.available() if a.spec.direct_access)

    def describe(self, usable_only: bool = False) -> list:
        source = self.available() if usable_only else self.all()
        return [a.describe() for a in source]

    def __contains__(self, agent_id: str) -> bool:
        return agent_id in self._agents

    def __len__(self) -> int:
        return len(self._agents)
