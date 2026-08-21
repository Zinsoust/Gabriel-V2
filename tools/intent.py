"""Outil de classification d'intention — routage de l'Orchestrateur.

`classify_intent` est déjà un classifieur déterministe réel : heuristique de
mots-clés et de regex, aucun appel LLM. Le brief fondateur de l'Orchestrateur
est explicite là-dessus — « toutes les demandes ne doivent pas déclencher le
même niveau d'intelligence » — classer une demande doit être instantané.
"""

from tools.base import FunctionTool, ToolInput, ToolSpec
from tools.registry import registry


def _classify_intent(message, has_psycho=False, has_strategy=False, has_createur=False):
    from agents.orchestrator.intent import classify_intent
    return classify_intent(message, has_psycho=has_psycho, has_strategy=has_strategy,
                           has_createur=has_createur)


CLASSIFY_INTENT = ToolSpec(
    id='intent.classify',
    name="Classification d'intention",
    description=(
        "Classe une demande utilisateur sans appel réseau : niveau de "
        "réponse (rapide/approfondi), agent à recommander, raison, "
        "confiance — pour décider si une orientation vers un agent "
        "spécialisé s'impose avant de répondre."),
    category='intent',
    inputs=(
        ToolInput('message', "Message de l'utilisateur"),
        ToolInput('has_psycho', "Une analyse Psychologue existe déjà dans le workspace",
                  required=False),
        ToolInput('has_strategy', "Une stratégie existe déjà", required=False),
        ToolInput('has_createur', "Un contenu existe déjà", required=False),
    ),
    output="{kind, level, agent, reason, confidence}",
    deterministic=True,
    parallel_safe=True,
    cacheable=True,
    timeout_s=None,
)


def register_all() -> None:
    registry.register(FunctionTool(CLASSIFY_INTENT, _classify_intent))


register_all()
