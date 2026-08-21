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




def _plan_context_access(message, intent, availability, memory=None):
    from agents.orchestrator.context_access import plan_context_access
    return plan_context_access(message, intent, availability, memory)


def _build_handoff(agent, message, business_context=None, has_psycho=False,
                   has_strategy=False):
    from agents.orchestrator.intent import build_handoff
    return build_handoff(agent, message, business_context=business_context,
                         has_psycho=has_psycho, has_strategy=has_strategy)


PLAN_CONTEXT_ACCESS = ToolSpec(
    id='intent.plan_context_access',
    name="Sélection des rapports à relire",
    description=(
        "Décide quels rapports d'agents une demande justifie de relire — "
        "aucun par défaut. Évite de traiter un rapport comme un contexte "
        "implicite à chaque message, et rend explicite d'où vient une "
        "recommandation."),
    category='intent',
    inputs=(
        ToolInput('message', "Message de l'utilisateur"),
        ToolInput('intent', "Sortie de intent.classify"),
        ToolInput('availability', "Rapports existants : {psychologue: bool, ...}"),
        ToolInput('memory', "Mémoire conversationnelle, pour résoudre une "
                            "relance courte à partir du tour précédent",
                  required=False),
    ),
    output="{use_agent_context: bool, agents: [...], reason: str}",
    deterministic=True,
    parallel_safe=True,
    cacheable=True,
    timeout_s=None,
)

BUILD_HANDOFF = ToolSpec(
    id='intent.build_handoff',
    name="Passage de relais vers un agent",
    description=(
        "Construit le paquet compact transmis à un agent spécialisé : "
        "l'objectif, le contexte business utile et ce qui a déjà été "
        "produit en amont — jamais l'historique brut."),
    category='intent',
    inputs=(
        ToolInput('agent', "Agent destinataire"),
        ToolInput('message', "Demande de l'utilisateur"),
        ToolInput('business_context', "Contexte business connu", required=False),
        ToolInput('has_psycho', "Une analyse existe déjà", required=False),
        ToolInput('has_strategy', "Une stratégie existe déjà", required=False),
    ),
    output="{user_goal, target_agent, source_agent, known_context, upstream_done}",
    deterministic=True,
    parallel_safe=True,
    cacheable=True,
    timeout_s=None,
)


def register_all() -> None:
    registry.register(FunctionTool(CLASSIFY_INTENT, _classify_intent))
    registry.register(FunctionTool(PLAN_CONTEXT_ACCESS, _plan_context_access))
    registry.register(FunctionTool(BUILD_HANDOFF, _build_handoff))


register_all()
