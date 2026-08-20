"""Outils d'analyse d'audience — la couche déterministe du Psychologue.

Ces trois capacités calculaient déjà tout ce qui est calculable **sans IA**
avant que le moindre modèle ne soit sollicité. C'est exactement la séparation
que vise la doctrine : le déterministe reste déterministe, le LLM n'intervient
que pour interpréter.

Aucun algorithme n'est modifié ici. Chaque outil enveloppe la fonction
existante de ``core.analyzer``, lui donne une carte d'identité et une entrée
validée. C'est délibéré : on extrait d'abord, on refactore éventuellement plus
tard — jamais les deux en même temps.
"""

from __future__ import annotations

from tools.base import FunctionTool, ToolInput, ToolSpec
from tools.registry import registry

CATEGORY = "audience"


def _score_comments(comments, nlp_data=None, title=""):
    from core.analyzer import score_comments_math
    return score_comments_math(comments, nlp_data, title)


def _compute_kpis(comments, scores, title=""):
    from core.analyzer import calculate_math_kpis
    kpis, distribution = calculate_math_kpis(comments, scores, title)
    # La fonction historique rend un tuple. Un outil doit rendre une valeur
    # nommée : un tuple oblige l'appelant à connaître l'ordre des éléments,
    # ce qu'un plan généré ne peut pas deviner.
    return {"kpis": kpis, "distribution": distribution}


def _compute_dashboard(scored_comments, nlp_data=None, total_comments=0, title=""):
    from core.analyzer import _compute_dashboard as _impl
    return _impl(scored_comments, nlp_data, total_comments, title)


score_comments = registry.register(FunctionTool(
    ToolSpec(
        id="audience.score_comments",
        name="Scoring des commentaires",
        description=(
            "Note chaque commentaire (sentiment VADER pondéré par la pertinence "
            "sémantique et les likes) et lui attache émotion, posture et signaux "
            "marketing détectés. Aucun appel de modèle."
        ),
        category=CATEGORY,
        inputs=(
            ToolInput("comments", "Liste de commentaires bruts {text, likes}"),
            ToolInput("nlp_data", "Signaux du pipeline NLP (pertinence, clusters)", required=False),
            ToolInput("title", "Titre du contenu analysé, pour la pertinence", required=False),
        ),
        output="Liste de commentaires enrichis (score, émotion, posture, signaux, poids d'engagement)",
        deterministic=True,
        parallel_safe=True,
        cacheable=True,
    ),
    _score_comments,
))

compute_kpis = registry.register(FunctionTool(
    ToolSpec(
        id="audience.compute_kpis",
        name="KPIs d'audience",
        description=(
            "Calcule les six indicateurs d'audience (engagement, authenticité, "
            "polarisation, opportunité, alignement, persistance). Chaque KPI "
            "expose sa formule et ses variables."
        ),
        category=CATEGORY,
        inputs=(
            ToolInput("comments", "Liste de commentaires bruts"),
            ToolInput("scores", "Scores numériques issus du scoring"),
            ToolInput("title", "Titre du contenu analysé", required=False),
        ),
        output="{kpis, distribution} — six KPIs avec formule, et répartition en cinq paliers",
        deterministic=True,
        parallel_safe=True,
        cacheable=True,
    ),
    _compute_kpis,
))

compute_dashboard = registry.register(FunctionTool(
    ToolSpec(
        id="audience.compute_dashboard",
        name="Tableau de bord d'audience",
        description=(
            "Agrège les métriques d'audience : répartitions sentiment / émotion / "
            "posture, polarisation, opportunité, confiance, bruit, ainsi que les "
            "signaux pondérés par l'engagement (résonance par camp, densité "
            "argumentative, moquerie, ironie, champs lexicaux)."
        ),
        category=CATEGORY,
        inputs=(
            ToolInput("scored_comments", "Commentaires enrichis par le scoring"),
            ToolInput("nlp_data", "Signaux du pipeline NLP", required=False),
            ToolInput("total_comments", "Nombre total de commentaires collectés", required=False),
            ToolInput("title", "Titre du contenu analysé", required=False),
        ),
        output="Dictionnaire de métriques agrégées prêtes pour l'affichage et l'interprétation",
        deterministic=True,
        parallel_safe=True,
        cacheable=True,
    ),
    _compute_dashboard,
))
