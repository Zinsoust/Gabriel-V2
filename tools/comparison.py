"""Outil de comparaison multi-sources — le cœur mesurable de la Cross Analyse.

`build_cross_analysis` ne produit aucune interprétation générative : elle
compte, compare et conserve la preuve par source. C'est déjà la fonction la
mieux testée du dépôt (validations explicites sur le nombre de sources,
l'unicité des identifiants, la forme des entrées) — l'enveloppe n'ajoute
rien, elle rend cette rigueur consultable par un planificateur.
"""

from tools.base import FunctionTool, ToolInput, ToolSpec
from tools.registry import registry


def _compare_sources(source_analyses):
    from core.cross_analysis import build_cross_analysis
    return build_cross_analysis(source_analyses)


COMPARE_SOURCES = ToolSpec(
    id='comparison.compare_sources',
    name='Comparaison multi-sources',
    description=(
        "Compare 2 à 5 analyses d'audience déjà produites : convergences, "
        "divergences, oppositions et score de confiance global, avec la "
        "preuve par source pour chaque signal retenu."),
    category='comparison',
    inputs=(
        ToolInput('source_analyses',
                  "Liste de 2 à 5 analyses source, chacune portant un "
                  "source_id unique (voir core/cross_analysis.py)"),
    ),
    output=(
        "{shared_*, divergent_*, stance_oppositions, confidence_score, "
        "data_quality, evidence_index, ...} — voir core/cross_analysis.py"),
    deterministic=True,
    parallel_safe=True,
    cacheable=True,   # mêmes analyses source → même comparaison
    timeout_s=None,   # local, aucun réseau ni IA
)


def register_all() -> None:
    registry.register(FunctionTool(COMPARE_SOURCES, _compare_sources))


register_all()
