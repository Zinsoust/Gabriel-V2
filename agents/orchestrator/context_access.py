"""Sélection déterministe des sources d'agents pour une réponse Gabriel.

Les résultats du Psychologue, du Stratège et du Créateur restent liés au même
workspace. L'Orchestrateur ne les charge que lorsqu'une question les appelle :
cela évite d'alourdir chaque échange, réduit l'exposition de données et rend
explicite la provenance d'une recommandation.
"""

from __future__ import annotations

import unicodedata
from typing import Any, Dict, List, Optional


_ALL_SIGNALS = (
    "synthese", "resume", "recap", "compare", "coherence", "coherent",
    "contradiction", "croise", "ensemble", "ce que l on sait", "qu avons nous",
)
_AGENT_SIGNALS = {
    "psychologue": ("psychologue", "analyse audience", "insight audience", "emotion", "persona"),
    "stratege": ("stratege", "strategie existante", "decision recommandee", "prix recommande", "positionnement retenu"),
    "createur": ("createur", "contenu genere", "texte genere", "livrable cree", "version du contenu"),
}
_FOLLOW_UP_SIGNALS = (
    "cette decision", "ce resultat", "cela", "ca", "coherent", "contradiction",
    "est ce que ca", "pourquoi", "quel risque", "quel prix",
)
_FOLLOW_UP_BY_AGENT = {
    "psychologue": ("cette audience", "ces emotions", "ces emotion", "ce persona", "cette cible"),
    "stratege": ("cette decision", "quel risque", "quel prix", "ce positionnement", "ce plan"),
    "createur": ("ce contenu", "ce texte", "cette version", "ce livrable"),
}


def _norm(value: Any) -> str:
    text = unicodedata.normalize("NFD", str(value or "").lower())
    return "".join(char for char in text if unicodedata.category(char) != "Mn")


def plan_context_access(message: str, intent: Dict[str, Any],
                        availability: Dict[str, bool],
                        memory: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Retourne les rapports à lire pour la demande courante, ou aucun.

    Une simple demande de création ou de conseil ne force jamais la lecture des
    rapports. Les sources sont lues si l'utilisateur demande explicitement à
    les interroger, à les synthétiser, ou s'il pose une relance qui ne peut être
    comprise sans le résultat d'agent déjà produit dans cette conversation.
    """
    text = _norm(message)
    availability = availability if isinstance(availability, dict) else {}
    memory = memory if isinstance(memory, dict) else {}
    available = [agent for agent in ("psychologue", "stratege", "createur")
                 if availability.get(agent)]
    if not available:
        return {"use_agent_context": False, "agents": [], "reason": "no_available_outputs"}

    selected: List[str] = []
    if any(signal in text for signal in _ALL_SIGNALS) or intent.get("kind") == "transversal":
        selected = available
        reason = "transversal_request"
    else:
        for agent, signals in _AGENT_SIGNALS.items():
            if agent in available and any(signal in text for signal in signals):
                selected.append(agent)
        if selected:
            reason = "explicit_agent_reference"
        else:
            for agent, signals in _FOLLOW_UP_BY_AGENT.items():
                if agent in available and any(signal in text for signal in signals):
                    selected.append(agent)
            if selected:
                reason = "targeted_follow_up"
            elif any(signal in text for signal in _FOLLOW_UP_SIGNALS):
                # Une relance très courte ("est-ce cohérent ?") n'ouvre pas
                # tous les rapports disponibles. Elle ne retrouve que les
                # rapports réellement consultés au tour précédent.
                last_context = memory.get("last_context_agents")
                last_context = last_context if isinstance(last_context, list) else []
                selected = [agent for agent in available if agent in last_context]
                reason = "conversation_follow_up" if selected else "direct_conversation"
            else:
                reason = "direct_conversation"

    selected = [agent for index, agent in enumerate(selected) if agent in available and agent not in selected[:index]]
    return {
        "use_agent_context": bool(selected),
        "agents": selected,
        "reason": reason,
    }
