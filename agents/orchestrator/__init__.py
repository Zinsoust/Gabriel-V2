# ═══════════════════════════════════════════════════════════════════════════
# L'ORCHESTRATEUR — cerveau de coordination (package)
#
# L'Orchestrateur ne fait pas le travail de fond des agents. Il comprend la
# demande, qualifie le niveau de réponse nécessaire, oriente vers le bon
# bureau et prépare le contexte à transmettre. Les analyses profondes restent
# la propriété du Psychologue, du Stratège et du Créateur.
#
# Ce package est ADDITIF : la route /orchestrator_chat existante continue de
# fonctionner. On enrichit sa réponse (recommandation + niveau) sans rien
# retirer.
# ═══════════════════════════════════════════════════════════════════════════

from agents.orchestrator.intent import (
    classify_intent,
    build_recommendation,
    build_handoff,
    AGENTS,
    response_max_tokens,
)
from agents.orchestrator.mental_model import build_mental_model
from agents.orchestrator.decision import decide_help
# NB : ce module ne planifie aucune exécution — il rédige la consigne de
# structure et de voix de la réponse. Le planificateur d'exécution, qui
# lit les registres pour ordonner les agents, vit dans core/planner.py.
from agents.orchestrator.response_directive import build_response_directive
from agents.orchestrator.validator import validate_response
from agents.orchestrator.missions import build_mission
from agents.orchestrator.conversation_memory import (
    update_conversation_memory,
    format_conversation_memory,
)
from agents.orchestrator.context_access import plan_context_access

__all__ = [
    "classify_intent",
    "build_recommendation",
    "build_handoff",
    "AGENTS",
    "response_max_tokens",
    "build_mental_model",
    "decide_help",
    "build_response_directive",
    "validate_response",
    "build_mission",
    "update_conversation_memory",
    "format_conversation_memory",
    "plan_context_access",
]
