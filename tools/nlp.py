"""Outil NLP — vectorisation, clustering, signaux lexicaux, diversité.

`run_nlp_pipeline` est le point d'entrée déjà utilisé par le Psychologue.
Plus grande surface sans IA du dépôt : pertinence contextuelle, clustering
sémantique (KMeans à graine fixe), signaux lexicaux, diversité sémantique —
quatre calculs en un seul appel, aucun d'eux génératif.
"""

from tools.base import FunctionTool, ToolInput, ToolSpec
from tools.registry import registry


def _run_nlp_pipeline(comments, title=""):
    from core.nlp_engine import run_nlp_pipeline
    return run_nlp_pipeline(comments, title=title)


RUN_NLP_PIPELINE = ToolSpec(
    id='nlp.run_pipeline',
    name='Pipeline NLP',
    description=(
        "Calcule la pertinence contextuelle, les clusters sémantiques, les "
        "signaux lexicaux et la diversité sémantique d'un ensemble de "
        "commentaires — sans appel de modèle génératif."),
    category='nlp',
    inputs=(
        ToolInput('comments', "Liste de commentaires [{text, likes, ...}]"),
        ToolInput('title', "Sujet analysé, pour la pertinence contextuelle",
                  required=False),
    ),
    output=(
        "{relevance_scores, cluster_labels, cluster_summary, lexical, "
        "semantic_diversity, relevance_distribution, n_comments, "
        "embedding_mode, embedding_model}"),
    # Déterministe *pour un modèle stable* : le clustering fixe sa graine
    # (random_state=42) et la vectorisation sémantique est un modèle chargé,
    # pas généré. Le repli TF-IDF (modèle indisponible) est lui-même
    # déterministe.
    deterministic=True,
    parallel_safe=True,
    cacheable=True,
    timeout_s=None,   # local ; premier chargement du modèle sémantique lent,
                      # les appels suivants sont rapides
)


def register_all() -> None:
    registry.register(FunctionTool(RUN_NLP_PIPELINE, _run_nlp_pipeline))


register_all()
