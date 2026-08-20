"""Grille psychologique du Psychologue.

`GABRIEL_SYSTEM` (core/analyzer.py) n'est pas un catalogue de variantes comme
les disciplines de tonalité — c'est un cadre de lecture unique et
obligatoire, injecté sans condition aux cinq appels LLM du Psychologue :
quatre niveaux de compréhension humaine (Munroe, principes universels,
Frankl ; Jung, Kahneman, Maslow, Freud, Girard ; Haidt, Bourdieu, Durkheim ;
Godin, Miller, Sinek, Cialdini, Sutherland) et sept lois absolues.

Il se déclare tout de même comme un Skill, avec un catalogue à une seule
entrée toujours résolue : c'est le même mécanisme qu'un catalogue à
plusieurs variantes, seulement sans variante à choisir — ce qui évite
d'inventer une deuxième forme de Skill pour ce cas.
"""

from skills.base import CatalogSkill, SkillSpec
from skills.registry import registry


def _psychology_skill() -> CatalogSkill:
    from core.analyzer import GABRIEL_SYSTEM
    return CatalogSkill(
        spec=SkillSpec(
            id='psychology.human_understanding_grid',
            name='Grille de compréhension humaine',
            description=(
                "Cadre de lecture psychologique et socioculturel appliqué à "
                "chaque analyse de commentaires : quatre niveaux de "
                "compréhension humaine et sept lois absolues de fidélité aux "
                "données."),
            domain='psychology',
            source='core/analyzer.py:GABRIEL_SYSTEM',
            accepts_free_text=False,
            solves=(
                "Fournit le cadre de lecture commun à toutes les analyses du "
                "Psychologue — sans lui, chaque appel LLM lirait les "
                "commentaires sans grille de compréhension partagée."),
            when_to_use=(
                "Systématiquement, en tête de chaque prompt du Psychologue — "
                "il ne varie jamais selon l'analyse en cours."),
            required_info=(),
            methodology_summary=(
                "4 niveaux (essence humaine, psychologie profonde, société et "
                "culture, marketing et influence) + 7 lois absolues "
                "(fidélité radicale, profondeur, concision, non-évidence, "
                "actionnabilité, intégrité, intelligence émotionnelle)."),
            limitations=(
                "Catalogue à une seule entrée : il n'y a rien à choisir, "
                "contrairement aux Skills d'écriture. `render()` accepte "
                "n'importe quel argument et rend toujours le même texte."),
            output_format="Bloc de texte fixe à injecter en tête du prompt système.",
        ),
        catalog={'psychologue': GABRIEL_SYSTEM},
        # Une seule entrée, toujours résolue : ce Skill ne choisit rien, il
        # s'applique. Contrairement à un `default_key` (repli sur une demande
        # non reconnue), ici il n'y a jamais de demande à reconnaître.
        normalizer=lambda _requested: 'psychologue',
    )


def register_all() -> None:
    registry.register(_psychology_skill())
