"""Raisonnement stratégique du Stratège.

`_STRATEGE_SYSTEM` (agents/stratege.py), comme la grille du Psychologue,
n'est pas un catalogue de variantes : c'est un cadre unique et obligatoire —
3 postures de raisonnement (simplification radicale, produit et usage réel,
fiabilité), un pipeline nommé en 11 étapes, et une règle de langage contre
les identifiants techniques bruts.
"""

from skills.base import CatalogSkill, SkillSpec
from skills.registry import registry


def _strategy_skill() -> CatalogSkill:
    from agents.stratege import _STRATEGE_SYSTEM
    return CatalogSkill(
        spec=SkillSpec(
            id='strategy.decision_reasoning',
            name='Raisonnement de décision stratégique',
            description=(
                "Cadre de décision marketing immédiate : part toujours de la "
                "psychologie de l'audience, jamais de l'offre — 3 postures de "
                "raisonnement puis un pipeline en 11 étapes jusqu'au plan "
                "90 jours."),
            domain='strategy',
            source='agents/stratege.py:_STRATEGE_SYSTEM',
            accepts_free_text=False,
            solves=(
                "Transforme un rapport psychologique et un contexte business "
                "en décision marketing actionnable, ancrée dans des signaux "
                "réels plutôt que des généralités."),
            when_to_use=(
                "Systématiquement, en tête du prompt du Stratège — il ne "
                "varie jamais selon l'analyse en cours."),
            required_info=(),
            methodology_summary=(
                "Formule centrale (psychologie → problème → valeur → offre → "
                "format → action → monétisation) ; 3 postures (simplification "
                "radicale, produit et usage réel, fiabilité) ; pipeline en 11 "
                "étapes jusqu'au plan 90 jours ; règle de langage interdisant "
                "les identifiants techniques bruts dans le texte visible."),
            limitations=(
                "Catalogue à une seule entrée, comme "
                "psychology.human_understanding_grid : rien à choisir, le "
                "cadre s'applique tel quel. Sa règle de langage duplique — "
                "avec des variantes de formulation, pas au caractère près — "
                "trois blocs similaires dans core/analyzer.py, non unifiés "
                "ici : le faire changerait le texte réellement envoyé au "
                "modèle à plusieurs endroits, hors du périmètre d'une "
                "extraction mécanique."),
            output_format="Bloc de texte fixe à injecter en tête du prompt système.",
        ),
        catalog={'stratege': _STRATEGE_SYSTEM},
        normalizer=lambda _requested: 'stratege',
    )


def register_all() -> None:
    registry.register(_strategy_skill())
