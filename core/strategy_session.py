# ═══════════════════════════════════════════════════════════════════════════
# STRATEGY SESSION — le parcours stratégique complet (Phase 1)
#
# Une session stratégique = UN parcours de réflexion, de l'accueil jusqu'à
# l'export. Elle existe dès l'arrivée de l'utilisateur dans la Salle de
# Conseil et s'enrichit à chaque étape — elle n'est jamais recréée en cours
# de route.
#
# Ce module est la SOURCE DE VÉRITÉ du parcours :
#   - quelles étapes existent et dans quel ordre     → JOURNEY_STEPS
#   - où en est l'utilisateur                        → current_step
#   - ce que chaque étape a produit                  → les champs de contenu
#
# Séparation des responsabilités (volontaire, pour que les étapes suivantes
# s'ajoutent sans rien réécrire) :
#   - core/strategy_session.py (ce fichier) → le PARCOURS (états, transitions)
#   - agents/context_builder/*              → le CONTENU d'une étape donnée
#   - app.py                                → le TRANSPORT (routes HTTP)
#   - static/js/strategy-workspace.js       → l'AFFICHAGE de l'étape courante
#
# Aucune logique d'affichage ici, aucun appel LLM ici : uniquement l'état du
# parcours et ses règles de transition.
# ═══════════════════════════════════════════════════════════════════════════

from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional

# ── Le tunnel complet ────────────────────────────────────────────────────
#
# PHASE 1 : seule l'étape "welcome" est implémentée côté interface. Les
# suivantes sont déjà déclarées ici pour que l'ajout d'un écran soit une
# seule ligne à changer, jamais une refonte du parcours. Ne pas réordonner
# sans mettre à jour la migration correspondante.
JOURNEY_STEPS: List[str] = [
    "welcome",      # Accueil — Salle de Conseil (implémenté)
    "interview",    # Entretien stratégique
    "conversation", # Conversation
    "analysis",     # Analyse
    "summary",      # Synthèse
    "marketing",    # Marketing
    "branding",     # Branding
    "action_plan",  # Plan d'action
    "decision",     # Décision
    "export",       # Export
]

FIRST_STEP: str = JOURNEY_STEPS[0]

# Étapes réellement disponibles aujourd'hui. Tout le reste est déclaré mais
# pas encore ouvert : le serveur refuse d'y envoyer l'utilisateur, ce qui
# évite les états impossibles pendant que le parcours se construit.
IMPLEMENTED_STEPS: List[str] = ["welcome", "interview"]


def is_valid_step(step: str) -> bool:
    """Une étape connue du parcours (même pas encore implémentée)."""
    return step in JOURNEY_STEPS


def is_open_step(step: str) -> bool:
    """Une étape où l'on peut réellement envoyer l'utilisateur aujourd'hui."""
    return step in IMPLEMENTED_STEPS


def next_step(step: str) -> Optional[str]:
    """L'étape suivante dans le tunnel, ou None si on est à la fin."""
    if step not in JOURNEY_STEPS:
        return None
    index = JOURNEY_STEPS.index(step)
    if index + 1 >= len(JOURNEY_STEPS):
        return None
    return JOURNEY_STEPS[index + 1]


@dataclass
class StrategySession:
    """L'état complet d'un parcours stratégique.

    Les champs de contenu (conversation, analysis, marketing…) sont prévus
    dès maintenant et restent vides en Phase 1. Ils ne sont pas typés plus
    finement volontairement : chaque étape définira sa propre structure
    quand elle sera développée, sans imposer aujourd'hui un format qu'on
    devrait casser demain.
    """
    session_id:   str
    user_id:      str
    created_at:   str = ""
    updated_at:   str = ""
    folder_id:    str = ""
    current_step: str = FIRST_STEP

    # ── Contenu produit par chaque étape (vide en Phase 1) ───────────────
    conversation: List[Dict[str, Any]] = field(default_factory=list)
    analysis:     Dict[str, Any]       = field(default_factory=dict)
    marketing:    Dict[str, Any]       = field(default_factory=dict)
    branding:     Dict[str, Any]       = field(default_factory=dict)
    action_plan:  Dict[str, Any]       = field(default_factory=dict)
    decision:     Dict[str, Any]       = field(default_factory=dict)
    history:      List[Dict[str, Any]] = field(default_factory=list)

    def to_public_dict(self) -> Dict[str, Any]:
        """Forme envoyée au frontend. Contrat stable : l'interface ne lit que
        ces clés, jamais la structure de stockage."""
        data = asdict(self)
        data["steps"] = JOURNEY_STEPS
        data["is_open"] = is_open_step(self.current_step)
        return data


def advance(session: StrategySession, to_step: str) -> StrategySession:
    """Fait avancer le parcours, en refusant les étapes inconnues ou pas
    encore ouvertes. Retourne la session modifiée (jamais une copie : le
    parcours est un état unique, pas une valeur immuable).

    L'historique conserve chaque transition — c'est ce qui permettra plus
    tard de revenir en arrière sans perdre ce qui a été produit.
    """
    if not is_valid_step(to_step):
        raise ValueError("Étape inconnue du parcours : %s" % to_step)
    if not is_open_step(to_step):
        raise ValueError("Étape pas encore disponible : %s" % to_step)
    if to_step == session.current_step:
        return session
    session.history.append({"from": session.current_step, "to": to_step})
    session.current_step = to_step
    return session
