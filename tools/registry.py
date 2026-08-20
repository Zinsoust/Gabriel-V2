"""Catalogue des outils disponibles.

PURPOSE
    Permettre à Gabriel Core de répondre à : quels outils existent, que font-ils,
    de quoi ont-ils besoin, lesquels puis-je lancer en parallèle, et qui a le
    droit de les utiliser.

NON-RESPONSIBILITIES
    - ne choisit pas quel outil employer (rôle du Router / Planner) ;
    - n'exécute rien lui-même : il rend un outil, l'appelant l'exécute.
"""

from __future__ import annotations

from typing import Iterable, Optional

from tools.base import Tool, ToolError


class ToolNotFound(ToolError, KeyError):
    """Aucun outil ne porte cet identifiant."""


class ToolNotAllowed(ToolError, PermissionError):
    """L'outil existe mais n'est pas ouvert à cet agent."""


class ToolRegistry:
    """Registre en mémoire. Un outil déclaré deux fois est une erreur : deux
    implémentations sous un même identifiant se masqueraient silencieusement."""

    def __init__(self):
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> Tool:
        tool_id = tool.spec.id
        if tool_id in self._tools:
            raise ValueError(f"Outil déjà enregistré : {tool_id}")
        self._tools[tool_id] = tool
        return tool

    def get(self, tool_id: str, *, agent: Optional[str] = None) -> Tool:
        """Rend un outil. Si ``agent`` est fourni, vérifie l'autorisation.

        Deux erreurs distinctes — « inconnu » et « non autorisé » — parce que
        les confondre empêcherait de diagnostiquer une permission manquante.
        """
        try:
            tool = self._tools[tool_id]
        except KeyError:
            connus = ', '.join(sorted(self._tools)) or '(aucun)'
            raise ToolNotFound(f"Outil inconnu : {tool_id} (connus : {connus})")
        if agent is not None and not tool.spec.is_allowed_for(agent):
            raise ToolNotAllowed(
                f"L'agent {agent} n'est pas autorisé à utiliser {tool_id}"
            )
        return tool

    def all(self) -> tuple[Tool, ...]:
        return tuple(self._tools[i] for i in sorted(self._tools))

    def for_agent(self, agent: str) -> tuple[Tool, ...]:
        return tuple(t for t in self.all() if t.spec.is_allowed_for(agent))

    def by_category(self, category: str) -> tuple[Tool, ...]:
        return tuple(t for t in self.all() if t.spec.category == category)

    def categories(self) -> tuple[str, ...]:
        return tuple(sorted({t.spec.category for t in self.all()}))

    def describe(self, agent: Optional[str] = None) -> list[dict]:
        """Catalogue sérialisable — la vue dont disposera le Planner."""
        tools: Iterable[Tool] = self.for_agent(agent) if agent else self.all()
        return [t.spec.describe() for t in tools]

    def __len__(self) -> int:
        return len(self._tools)

    def __contains__(self, tool_id: object) -> bool:
        return tool_id in self._tools


# Registre du processus. Les modules d'outils s'y déclarent à l'import.
registry = ToolRegistry()
