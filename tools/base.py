"""Contrat d'un outil Gabriel.

PURPOSE
    Rendre les capacités de Gabriel énumérables et interrogeables. Aujourd'hui
    chaque capacité est une fonction Python importée en dur par l'agent qui
    l'utilise : Gabriel ne peut pas *choisir* un outil, faute de catalogue.

RESPONSIBILITIES
    - décrire une capacité (identité, entrées, sortie, contraintes) ;
    - valider les entrées avant exécution ;
    - exposer ce qu'un futur planificateur doit savoir : est-ce déterministe,
      parallélisable, coûteux, réservé à certains agents.

NON-RESPONSIBILITIES
    - n'implémente aucune logique métier (un outil enveloppe du code existant) ;
    - ne décide pas quand s'exécuter (c'est le rôle du Router / Planner) ;
    - n'appelle aucun LLM directement (voir core.llm_client).

Chaque champ du contrat répond à une question que Gabriel Core devra poser :
« que fait cet outil ? », « de quoi a-t-il besoin ? », « puis-je le lancer en
parallèle ? », « qui a le droit de l'utiliser ? ». Un champ qui ne répond à
aucune question réelle n'a pas sa place ici.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, Optional


class ToolError(RuntimeError):
    """Échec d'exécution d'un outil."""


class ToolInputError(ToolError, ValueError):
    """Entrées invalides — inutile de réessayer, il faut corriger l'appel."""


@dataclass(frozen=True)
class ToolInput:
    """Une entrée attendue par un outil."""
    name: str
    description: str
    required: bool = True


@dataclass(frozen=True)
class ToolSpec:
    """Carte d'identité d'un outil, lisible par un humain comme par le Core."""

    id: str
    name: str
    description: str
    category: str
    inputs: tuple[ToolInput, ...]
    output: str

    # Déterministe = même entrée, même sortie, sans appel de modèle. C'est la
    # distinction la plus structurante de la doctrine : ce qui est calculable
    # ne doit jamais être délégué à un LLM.
    deterministic: bool = True

    # Sûr en parallèle : aucun état partagé muté, aucune limite de débit
    # externe à respecter. Le futur graphe d'exécution s'appuiera dessus.
    parallel_safe: bool = True

    # Résultat réutilisable pour des entrées identiques.
    cacheable: bool = False

    # None = pas de limite (calcul local). Renseigné pour tout ce qui sort
    # du processus.
    timeout_s: Optional[float] = None

    # Vide = ouvert à tous. Sinon, liste blanche d'agents.
    allowed_agents: tuple[str, ...] = ()

    # Coût réel non nul d'un appel — quota API, facturation, débit limité.
    # Texte libre plutôt qu'un nombre : le coût d'un outil externe se mesure
    # rarement dans une seule unité (quota YouTube ≠ $ OpenAI ≠ débit RapidAPI).
    # Vide = gratuit / local.
    cost_hint: str = ''

    def is_allowed_for(self, agent_id: str) -> bool:
        """Un outil sans liste blanche est ouvert ; sinon l'agent doit y figurer."""
        return not self.allowed_agents or agent_id in self.allowed_agents

    def required_inputs(self) -> tuple[str, ...]:
        return tuple(i.name for i in self.inputs if i.required)

    def describe(self) -> dict:
        """Forme sérialisable — ce qu'un planificateur lira pour raisonner."""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "category": self.category,
            "inputs": [
                {"name": i.name, "description": i.description, "required": i.required}
                for i in self.inputs
            ],
            "output": self.output,
            "deterministic": self.deterministic,
            "parallel_safe": self.parallel_safe,
            "cacheable": self.cacheable,
            "timeout_s": self.timeout_s,
            "allowed_agents": list(self.allowed_agents),
            "cost_hint": self.cost_hint,
        }


class Tool(ABC):
    """Base d'un outil. ``run()`` valide puis délègue à ``_execute()``."""

    spec: ToolSpec

    def run(self, **kwargs) -> Any:
        """Point d'entrée unique : valide les entrées, puis exécute.

        La validation est faite ici plutôt que dans chaque outil : une entrée
        manquante doit produire un message clair et actionnable, jamais un
        ``KeyError`` remonté du fond de l'implémentation.
        """
        missing = [name for name in self.spec.required_inputs() if name not in kwargs]
        if missing:
            raise ToolInputError(
                f"{self.spec.id} : entrée(s) requise(s) manquante(s) — {', '.join(missing)}"
            )
        known = {i.name for i in self.spec.inputs}
        unexpected = [k for k in kwargs if k not in known]
        if unexpected:
            # Une entrée inconnue est presque toujours une faute de frappe sur
            # un nom de paramètre : l'ignorer ferait tourner l'outil sur des
            # valeurs par défaut sans que personne ne s'en aperçoive.
            raise ToolInputError(
                f"{self.spec.id} : entrée(s) inconnue(s) — {', '.join(unexpected)} "
                f"(attendues : {', '.join(sorted(known))})"
            )
        return self._execute(**kwargs)

    @abstractmethod
    def _execute(self, **kwargs) -> Any:
        raise NotImplementedError


class FunctionTool(Tool):
    """Outil qui enveloppe une fonction existante, sans la modifier.

    C'est le mode d'extraction par défaut : on ne réécrit pas l'algorithme,
    on lui donne une carte d'identité et une porte d'entrée validée.
    """

    def __init__(self, spec: ToolSpec, fn: Callable[..., Any]):
        self.spec = spec
        self._fn = fn

    def _execute(self, **kwargs) -> Any:
        return self._fn(**kwargs)
