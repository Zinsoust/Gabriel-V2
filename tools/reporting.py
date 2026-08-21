"""Outils de rapport — production de livrables PDF.

Deux formats déjà servis par des routes d'export : le rapport d'analyse
complet et la stratégie seule. Purs au sens strict — un dictionnaire entre,
des octets sortent : ni réseau, ni écriture disque, ni appel de modèle.

Le contrat honnête tient en un point : ces outils dépendent de `reportlab`.
Absent, ils lèvent une `ImportError` explicite plutôt que de rendre un
fichier vide — comportement d'origine, conservé.
"""

from tools.base import FunctionTool, ToolInput, ToolSpec
from tools.registry import registry


def _generate_analysis_report(entry, include_strategy=True):
    from services.gen_pdf import generate_analysis_pdf
    return generate_analysis_pdf(entry, include_strategy=include_strategy)


def _generate_strategy_report(strategy_data, analysis_entry=None):
    from services.gen_pdf import generate_strategy_pdf
    return generate_strategy_pdf(strategy_data, analysis_entry)


GENERATE_ANALYSIS_REPORT = ToolSpec(
    id='reporting.analysis_pdf',
    name="Rapport d'analyse (PDF)",
    description=(
        "Produit le rapport PDF complet d'une analyse d'audience, avec la "
        "stratégie associée si elle existe."),
    category='reporting',
    inputs=(
        ToolInput('entry', "Entrée d'analyse complète (résultat + métadonnées)"),
        ToolInput('include_strategy', "Inclure la stratégie liée (défaut : oui)",
                  required=False),
    ),
    output="Octets du fichier PDF",
    deterministic=True,   # mêmes données, même document
    parallel_safe=True,   # chaque appel écrit dans son propre tampon mémoire
    # Volontairement non caché : un PDF pèse lourd en mémoire pour un gain
    # nul — il est produit une fois, téléchargé, puis oublié.
    cacheable=False,
    timeout_s=None,       # local, aucun réseau
)

GENERATE_STRATEGY_REPORT = ToolSpec(
    id='reporting.strategy_pdf',
    name='Rapport de stratégie (PDF)',
    description="Produit le PDF d'une stratégie seule, sans l'analyse complète.",
    category='reporting',
    inputs=(
        ToolInput('strategy_data', "Stratégie produite par le Stratège"),
        ToolInput('analysis_entry', "Analyse d'origine, pour le contexte",
                  required=False),
    ),
    output="Octets du fichier PDF",
    deterministic=True,
    parallel_safe=True,
    cacheable=False,
    timeout_s=None,
)


def register_all() -> None:
    registry.register(FunctionTool(GENERATE_ANALYSIS_REPORT, _generate_analysis_report))
    registry.register(FunctionTool(GENERATE_STRATEGY_REPORT, _generate_strategy_report))


register_all()
