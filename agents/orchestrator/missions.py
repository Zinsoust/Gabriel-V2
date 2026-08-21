"""Contrat de mission de l'Orchestrateur.

Ce module ne lance aucun agent et ne prend aucune décision de présentation.
Il transforme une intention déjà qualifiée en une mission lisible par l'API et
l'interface. Le lancement reste effectué par les pipelines existants, qui
conservent leurs contrôles d'accès, de crédits et de persistance.
"""

from __future__ import annotations

import re
from typing import Any, Dict, Optional


_URL_RE = re.compile(r"https?://[^\s<>\]\[\)\(\"']+", re.IGNORECASE)


_AGENT_DETAILS = {
    "psychologue": {
        "name": "Psychologue",
        "description": "Analyse les émotions, motivations et freins de l’audience.",
    },
    "stratege": {
        "name": "Stratège",
        "description": "Transforme les enseignements en choix stratégiques.",
    },
    "createur": {
        "name": "Créateur",
        "description": "Produit les contenus à partir de la décision retenue.",
    },
}


def _source_from_message(message: str) -> Optional[Dict[str, str]]:
    """Extrait une source exploitable par le pipeline Psychologue existant."""
    url_match = _URL_RE.search(message or "")
    if url_match:
        url = url_match.group(0).rstrip(".,;:!?")
        normalized = url.lower()
        if "youtube.com" in normalized or "youtu.be" in normalized:
            return {"source": "youtube", "content": url, "label": "Lien YouTube"}
        if "instagram.com" in normalized:
            return {"source": "instagram", "content": url, "label": "Lien Instagram"}
        if "tiktok.com" in normalized:
            return {"source": "tiktok", "content": url, "label": "Lien TikTok"}

    # Un bloc suffisamment long et multi-lignes est très probablement un
    # collage de commentaires. Une phrase de demande ne doit jamais être
    # envoyée au Psychologue comme si elle était une donnée d'audience.
    compact = (message or "").strip()
    if len(compact) >= 350 and compact.count("\n") >= 2:
        return {"source": "text", "content": compact, "label": "Commentaires collés"}
    return None


def _mission_base(mission_id: str, title: str, objective: str, agent: str) -> Dict[str, Any]:
    details = _AGENT_DETAILS[agent]
    return {
        "id": mission_id,
        "title": title,
        "objective": objective,
        "status": "awaiting_input",
        "selected_agents": [{
            "id": agent,
            "name": details["name"],
            "description": details["description"],
            "status": "pending",
        }],
        "deliverables": [],
        "inputs": [],
        "panel": {"type": "mission_summary"},
    }


def build_mission(intent: Dict[str, Any], message: str, mission_id: str,
                  availability: Optional[Dict[str, bool]] = None) -> Optional[Dict[str, Any]]:
    """Construit une mission lorsqu'une demande exige un agent.

    L'Orchestrateur répond directement aux questions couvertes par le contexte.
    Une mission n'apparaît que pour une intention spécialisée. Le parcours
    Audience est exécutable de bout en bout car il est relié au pipeline
    ``/api/v2/agents/psychologue/analyze``. Les missions Stratège et Créateur posent leurs
    prérequis sans feindre de lancer un travail qui ne serait pas prêt.
    """
    agent = intent.get("agent")
    if agent not in _AGENT_DETAILS:
        return None

    availability = availability or {}
    if agent == "psychologue":
        mission = _mission_base(
            mission_id,
            "Analyse d’audience",
            "Comprendre les émotions, motivations et freins qui structurent cette audience.",
            agent,
        )
        mission["panel"] = {"type": "audience_analysis"}
        mission["deliverables"] = [
            {"title": "Lecture émotionnelle de l’audience", "type": "Analyse"},
            {"title": "Personas et tensions principales", "type": "Insights"},
            {"title": "Recommandations d’angle", "type": "Décision"},
        ]
        source = _source_from_message(message)
        if source:
            mission.update({
                "status": "ready",
                "selected_agents": [{**mission["selected_agents"][0], "status": "selected"}],
                "inputs": [{"id": "source", "label": source["label"], "value": source["content"]}],
                # Le front ne choisit pas l'agent : il exécute uniquement la
                # commande explicitement décidée par Gabriel dans ce contrat.
                "execution": {
                    "endpoint": "/api/v2/agents/psychologue/analyze",
                    "method": "POST",
                    "label": "Lancer l’analyse",
                    "payload": {"source": source["source"], "content": source["content"]},
                },
            })
        else:
            mission["inputs"] = [{
                "id": "source",
                "label": "Source d’audience requise",
                "help": "Collez un lien YouTube, Instagram ou TikTok, ou un ensemble de commentaires.",
            }]
        return mission

    if agent == "stratege":
        mission = _mission_base(
            mission_id,
            "Décision stratégique",
            "Relier l’audience, l’offre et le marché pour choisir une direction nette.",
            agent,
        )
        mission["panel"] = {"type": "strategy_decision"}
        mission["deliverables"] = [
            {"title": "Décision stratégique centrale", "type": "Décision"},
            {"title": "Positionnement et message", "type": "Stratégie"},
            {"title": "Plan d’action priorisé", "type": "Plan"},
        ]
        if availability.get("psychologue"):
            mission["inputs"] = [{
                "id": "business_context",
                "label": "Contexte business à compléter",
                "help": "Gabriel vérifiera l’offre, la cible et l’objectif avant de lancer la décision.",
            }]
        else:
            mission["inputs"] = [{
                "id": "audience_analysis",
                "label": "Analyse d’audience requise",
                "help": "Gabriel commence par vérifier les données d’audience pour fonder la décision.",
            }]
        return mission

    mission = _mission_base(
        mission_id,
        "Production de contenu",
        "Transformer la stratégie validée en contenu adapté au canal et à l’objectif.",
        agent,
    )
    mission["panel"] = {"type": "content_production"}
    mission["deliverables"] = [
        {"title": "Contenu prêt à publier", "type": "Contenu"},
        {"title": "Variantes et angles", "type": "Variantes"},
    ]
    mission["inputs"] = [{
        "id": "content_brief",
        "label": "Format et objectif requis",
        "help": "Précisez le canal, le format et l’action attendue avant la production.",
    }]
    return mission
