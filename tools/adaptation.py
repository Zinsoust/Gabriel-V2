"""Outil d'adaptation Psychologue → Stratège.

`_build_psycho_context` réduit le rapport riche du Psychologue au sous-
ensemble structuré dont le Stratège a besoin (personas prioritaires,
peurs, aspirations, insights, signaux marketing, KPIs) ; `_psycho_query_text`
en dérive un résumé compact pour la recherche RAG et la critique. Les deux
sont toujours utilisées en chaîne — l'outil déclare la chaîne réelle.
"""

from tools.base import FunctionTool, ToolInput, ToolSpec
from tools.registry import registry


def _adapt_psycho_context(psycho_data):
    from agents.stratege import _build_psycho_context, _psycho_query_text
    context = _build_psycho_context(psycho_data)
    return {'context': context, 'query_text': _psycho_query_text(context)}


ADAPT_PSYCHO_CONTEXT = ToolSpec(
    id='adaptation.psycho_to_strategy_context',
    name='Adaptation Psychologue → Stratège',
    description=(
        "Réduit un rapport complet du Psychologue au sous-ensemble "
        "structuré nécessaire à une décision stratégique, et en dérive un "
        "résumé texte compact pour la recherche documentaire."),
    category='adaptation',
    inputs=(
        ToolInput('psycho_data', "Rapport complet du Psychologue"),
    ),
    output="{context: {...structuré...}, query_text: str}",
    deterministic=True,
    parallel_safe=True,
    cacheable=True,
    timeout_s=None,
)


def register_all() -> None:
    registry.register(FunctionTool(ADAPT_PSYCHO_CONTEXT, _adapt_psycho_context))


register_all()
