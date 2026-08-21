"""Immersion persona du Créateur.

Méthodologie construite ligne à ligne en Python (`build_writing_brief`), donc
invisible : dix angles nommés qui reconstituent la réalité intérieure d'une
personne — ce qui l'épuise, ce qu'elle espérait, ce qu'elle s'est dit pour ne
pas agir, ce qu'elle ne dit pas à voix haute — assemblés depuis les données du
Psychologue.

Ce qui est déclaré ici : le **cadrage** (fixe) et les **angles** (la méthode).
Ce qui ne l'est pas : l'assemblage des données, qui reste dans
`build_writing_brief`. Un Skill enseigne une méthode ; il ne recopie pas
soixante lignes de construction de chaîne, où la moindre divergence serait
invisible et durable.
"""

from skills.base import CatalogSkill, SkillSpec
from skills.registry import registry


# Les dix angles, dans l'ordre où la méthode les convoque. Ce sont les
# intitulés réellement écrits dans le prompt — pas une reformulation.
_ANGLES = (
    "Qui elle est",
    "Ce qui l'épuise chaque jour",
    "Ce qu'elle espérait et qui ne s'est pas passé",
    "Ce qu'elle s'est déjà dit pour ne pas agir",
    "Ce qu'elle veut vraiment (mais ne dit pas à voix haute)",
    "Ce qui la fait se lever le matin",
    "Ses mots à elle — utilise-les, pas les tiens",
    "Son état émotionnel dominant",
    "La vérité qu'elle ne s'est jamais dite à elle-même",
    "Le persona ciblé, quand il est fourni, devient la base exclusive",
)


def _persona_immersion_skill() -> CatalogSkill:
    from agents.createur import _PERSONA_IMMERSION
    return CatalogSkill(
        spec=SkillSpec(
            id='writing.persona_immersion',
            name='Immersion persona',
            description=(
                "Fait écrire depuis la perspective d'une personne précise "
                "plutôt qu'à son intention : « elle n'est pas ton audience, "
                "elle est toi, deux ans en arrière »."),
            domain='writing',
            source='agents/createur.py:_PERSONA_IMMERSION + build_writing_brief',
            accepts_free_text=False,
            solves=(
                "Empêche un contenu d'être écrit *sur* une audience au lieu "
                "d'être écrit *depuis* elle — la différence entre un texte "
                "qui décrit une frustration et un texte qui la fait "
                "reconnaître."),
            when_to_use=(
                "Pour toute génération de contenu adossée à une analyse "
                "d'audience, avant la rédaction elle-même."),
            # Le seul Skill dont les besoins en information sont réels et
            # nombreux : la méthode ne vaut que par les données qui la
            # nourrissent. Un angle sans donnée est simplement omis du prompt.
            required_info=(
                'brief.synthese', 'psychologie.frustrations',
                'emotions.espoir_decu', 'psychologie.objections_principales',
                'psychologie.desirs_caches', 'psychologie.motivations_profondes',
                'nlp.mots_frequents', 'emotions.repartition', 'brief.insight_cle',
                'persona (facultatif)',
            ),
            methodology_summary=(
                "Dix angles convoqués dans l'ordre pour reconstituer la "
                "réalité intérieure d'une personne : " + " · ".join(_ANGLES) + "."),
            allowed_tools=(),
            limitations=(
                "Seul le cadrage est déclaré ici ; l'assemblage des dix "
                "angles depuis les données du Psychologue reste dans "
                "`build_writing_brief`. Chaque angle dont la donnée manque "
                "est omis silencieusement du prompt — un rapport pauvre "
                "produit donc une immersion pauvre, sans que rien ne le "
                "signale."),
            output_format=(
                "En-tête de section fixe, suivi dans le prompt des angles "
                "réellement nourris par les données disponibles."),
        ),
        catalog={'createur': _PERSONA_IMMERSION},
        normalizer=lambda _requested: 'createur',
    )


def register_all() -> None:
    registry.register(_persona_immersion_skill())
