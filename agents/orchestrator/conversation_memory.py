"""Mémoire de travail, durable et strictement locale à une conversation.

Ce module est un *mini-programme* de l'Orchestrateur : il ne produit pas de
conseil et ne fait aucun appel réseau. Son rôle est de préserver les éléments
business explicitement formulés au fil de la discussion (offre, cible,
objectif, contrainte) afin que Gabriel ne perde pas le sujet après plusieurs
tours. Les rapports des agents ne sont pas recopiés ici : ils restent dans
leurs stockages métier et sont sélectionnés à la demande par ``context_access``.
"""

from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Optional


_FACT_LABELS = {
    "offre": ("offre", "produit", "service", "programme", "abonnement"),
    "cible": ("cible", "client", "audience", "persona", "entrepreneur", "marché"),
    "objectif": ("objectif", "résultat", "vendre", "vente", "croissance", "lancer"),
    "contrainte": ("contrainte", "budget", "temps", "équipe", "ressource", "prix"),
}
_TOPIC_LABELS = {
    "offre": ("offre", "produit", "service", "prix", "pricing", "positionnement"),
    "audience": ("audience", "cible", "client", "persona", "commentaire"),
    "stratégie": ("stratégie", "strategie", "décision", "decision", "plan"),
    "contenu": ("contenu", "post", "script", "email", "publication", "rédiger", "rediger"),
}


def _text(value: Any, limit: int = 420) -> str:
    return " ".join(str(value or "").split())[:limit].strip()


def _sentences(message: str) -> Iterable[str]:
    for sentence in re.split(r"(?<=[.!?])\s+|\n+", _text(message, 1200)):
        sentence = sentence.strip()
        if sentence:
            yield sentence


def _fact_from_message(message: str, signals: Iterable[str]) -> str:
    """Conserve une phrase de l'utilisateur, jamais une instruction système."""
    lowered = _text(message, 1200).lower()
    for sentence in _sentences(message):
        if any(signal in sentence.lower() for signal in signals):
            return _text(sentence, 280)
    return _text(message, 280) if any(signal in lowered for signal in signals) else ""


def _prior_facts(previous: Dict[str, Any]) -> Dict[str, List[str]]:
    raw = previous.get("facts") if isinstance(previous, dict) else {}
    result: Dict[str, List[str]] = {}
    if not isinstance(raw, dict):
        return result
    for key, values in raw.items():
        if key not in _FACT_LABELS or not isinstance(values, list):
            continue
        cleaned = [_text(value, 280) for value in values if _text(value, 280)]
        if cleaned:
            result[key] = cleaned[-3:]
    return result


def update_conversation_memory(previous: Dict[str, Any], message: str,
                               history: Iterable[Dict[str, Any]] = (),
                               folder: Optional[Dict[str, Any]] = None,
                               available_agents: Iterable[str] = ()) -> Dict[str, Any]:
    """Met à jour une mémoire compacte à persister avec la conversation.

    Les seuls faits mémorisés proviennent des messages ``user``. Cette règle
    évite qu'une réponse de modèle, ou le contenu d'un rapport, devienne une
    "vérité" conversationnelle persistante sans que l'utilisateur l'ait dit.
    """
    previous = previous if isinstance(previous, dict) else {}
    facts = _prior_facts(previous)
    current = _text(message, 1200)
    for name, signals in _FACT_LABELS.items():
        fact = _fact_from_message(current, signals)
        if not fact:
            continue
        known = facts.setdefault(name, [])
        if fact not in known:
            known.append(fact)
        facts[name] = known[-3:]

    topics = [topic for topic, signals in _TOPIC_LABELS.items()
              if any(signal in current.lower() for signal in signals)]
    previous_topics = previous.get("topics") if isinstance(previous.get("topics"), list) else []
    ordered_topics = []
    for topic in [*previous_topics, *topics]:
        if topic in _TOPIC_LABELS and topic not in ordered_topics:
            ordered_topics.append(topic)

    previous_turns = int(previous.get("turn_count") or 0)
    user_turns = sum(
        1 for item in history
        if isinstance(item, dict) and item.get("role") == "user" and _text(item.get("content"))
    )
    folder = folder if isinstance(folder, dict) else {}
    return {
        "version": 1,
        "turn_count": max(previous_turns + 1, user_turns + 1),
        "focus": current[:280],
        "topics": ordered_topics[-5:],
        "facts": facts,
        "workspace_objective": _text(folder.get("objective"), 280),
        "available_agent_outputs": sorted({
            agent for agent in available_agents
            if agent in {"psychologue", "stratege", "createur"}
        }),
    }


def format_conversation_memory(memory: Dict[str, Any]) -> str:
    """Formate la mémoire comme une référence factuelle, jamais comme une instruction."""
    memory = memory if isinstance(memory, dict) else {}
    parts = []
    objective = _text(memory.get("workspace_objective"), 280)
    if objective:
        parts.append(f"Objectif du workspace : {objective}")
    facts = memory.get("facts") if isinstance(memory.get("facts"), dict) else {}
    labels = {"offre": "Éléments sur l’offre", "cible": "Éléments sur la cible",
              "objectif": "Objectifs évoqués", "contrainte": "Contraintes évoquées"}
    for key in ("offre", "cible", "objectif", "contrainte"):
        values = facts.get(key) if isinstance(facts.get(key), list) else []
        values = [_text(value, 280) for value in values if _text(value, 280)]
        if values:
            parts.append(f"{labels[key]} : {' | '.join(values[-2:])}")
    topics = memory.get("topics") if isinstance(memory.get("topics"), list) else []
    if topics:
        parts.append(f"Sujets suivis : {', '.join(str(topic) for topic in topics[-5:])}")
    return "\n".join(parts) or "Aucune mémoire business explicite n’est encore établie."
