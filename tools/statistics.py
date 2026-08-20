"""Outil de livrables statistiques purs — zéro IA.

`compute_pure_statistical_deliverables` compose deux calculs déjà déclarés
(le scoring de `audience.score_comments` et le pipeline `nlp.run_pipeline`)
en six livrables publiables : positionnement, carte émotionnelle,
répartition des camps, signaux lexicaux dominants, clusters
comportementaux, distribution de pertinence — chacun avec son propre score
de confiance.
"""

from tools.base import FunctionTool, ToolInput, ToolSpec
from tools.registry import registry


def _compute_statistical_deliverables(layer1, nlp_data, comments):
    from core.nlp_engine import compute_pure_statistical_deliverables
    return compute_pure_statistical_deliverables(layer1, nlp_data, comments)


COMPUTE_STATISTICAL_DELIVERABLES = ToolSpec(
    id='statistics.compute_deliverables',
    name='Livrables statistiques',
    description=(
        "Calcule six livrables publiables (positionnement, carte "
        "émotionnelle, répartition des camps, signaux lexicaux, clusters "
        "comportementaux, distribution de pertinence) à partir des "
        "commentaires déjà scorés et du pipeline NLP — aucun appel IA."),
    category='statistics',
    inputs=(
        ToolInput('layer1', "Commentaires scorés (sortie de audience.score_comments)"),
        ToolInput('nlp_data', "Sortie de nlp.run_pipeline"),
        ToolInput('comments', "Commentaires bruts d'origine"),
    ),
    output=(
        "{positionnement_audience, carte_emotionnelle, repartition_camps, "
        "signaux_lexicaux_dominants, clusters_comportementaux, "
        "distribution_relevance} — {} si layer1 est vide"),
    deterministic=True,
    parallel_safe=True,
    cacheable=True,
    timeout_s=None,
)


def register_all() -> None:
    registry.register(FunctionTool(COMPUTE_STATISTICAL_DELIVERABLES,
                                   _compute_statistical_deliverables))


register_all()
