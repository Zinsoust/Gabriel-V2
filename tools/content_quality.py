"""Outil de contrôle qualité de contenu — 7 critères, zéro IA.

`Createur.quality_check_content` n'utilise jamais `self` : c'est une fonction
pure sous forme de méthode. Elle inclut un détecteur de formules « IA-
sounding » (patterns génériques du type « il est temps de », « libère ton
potentiel ») directement réutilisable par tout agent qui produit du texte,
pas seulement le Créateur.
"""

from tools.base import FunctionTool, ToolInput, ToolSpec
from tools.registry import registry


def _check_content_quality(content_result, psycho_data, strategy, content_type):
    from agents.createur import Createur
    return Createur().quality_check_content(content_result, psycho_data, strategy, content_type)


CHECK_CONTENT_QUALITY = ToolSpec(
    id='content_quality.check',
    name='Contrôle qualité de contenu',
    description=(
        "Vérifie 7 critères déterministes sur un contenu généré : ancrage "
        "psychologie/stratégie, présence d'un hook et d'un CTA, absence de "
        "formules génériques « IA-sounding », format correct."),
    category='content_quality',
    inputs=(
        ToolInput('content_result', "Contenu généré (dict), sera sérialisé pour l'analyse"),
        ToolInput('psycho_data', "Rapport du Psychologue, pour vérifier l'ancrage"),
        ToolInput('strategy', "Stratégie retenue, pour vérifier l'ancrage"),
        ToolInput('content_type', "Format demandé, pour vérifier sa validité"),
    ),
    output=(
        "{based_on_psychology, based_on_strategy, clear_hook, cta_present, "
        "not_generic, ai_free, format_correct} — 7 booléens"),
    deterministic=True,
    parallel_safe=True,
    cacheable=True,
    timeout_s=None,
)


def register_all() -> None:
    registry.register(FunctionTool(CHECK_CONTENT_QUALITY, _check_content_quality))


register_all()
