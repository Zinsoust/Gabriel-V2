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

__all__ = [
    "classify_intent",
    "build_recommendation",
    "build_handoff",
    "AGENTS",
    "response_max_tokens",
]
