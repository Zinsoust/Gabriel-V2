"""Outil anti-hallucination — vérification mécanique des références citées.

`ground_llm_output` ne réinterprète rien : une affirmation du LLM sans
ancrage réel dans les preuves mesurées n'est pas nuancée, elle est retirée,
avec un compte visible pour ne jamais faire passer un rejet pour un
silence. Utile à tout agent qui doit vérifier une sortie LLM contre des
preuves mesurées, pas seulement la Cross Analyse.
"""

from tools.base import FunctionTool, ToolInput, ToolSpec
from tools.registry import registry


def _ground_claims(parsed, cross_result):
    from core.cross_interpreter import ground_llm_output
    return ground_llm_output(parsed, cross_result)


GROUND_CLAIMS_AGAINST_EVIDENCE = ToolSpec(
    id='grounding.ground_claims',
    name='Vérification des affirmations contre les preuves',
    description=(
        "Retire d'une sortie LLM toute affirmation dont l'insight_id ou les "
        "source_ids cités ne correspondent à aucune preuve réellement "
        "mesurée — jamais une reformulation, toujours un retrait compté."),
    category='grounding',
    inputs=(
        ToolInput('parsed', "Sortie JSON du LLM à vérifier (interprétation, personas...)"),
        ToolInput('cross_result', "Résultat mesuré de comparison.compare_sources, "
                                  "porteur des source_ids et de evidence_index"),
    ),
    output=(
        "{executive_summary, common_psychological_core, "
        "convergence_interpretations, divergence_interpretations, "
        "cross_personas, validation: {*_rejected: int}}"),
    deterministic=True,
    parallel_safe=True,
    cacheable=True,
    timeout_s=None,
)


def register_all() -> None:
    registry.register(FunctionTool(GROUND_CLAIMS_AGAINST_EVIDENCE, _ground_claims))


register_all()
