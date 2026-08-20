"""Savoir-faire d'écriture du Créateur.

Ces méthodologies existent déjà et sont éprouvées en production. On ne les
réécrit pas : on les *déclare*. Les catalogues sont référencés par leur objet
d'origine dans `agents.createur`, jamais recopiés — une divergence entre le
Skill et le code historique serait invisible et durable.
"""

from skills.base import CatalogSkill, SkillSpec
from skills.registry import registry


def _tone_skill() -> CatalogSkill:
    from agents.createur import _TONE_ALIASES, _TONE_DISCIPLINES
    return CatalogSkill(
        spec=SkillSpec(
            id='writing.tone_discipline',
            name="Disciplines de tonalité",
            description=(
                "Chaque tonalité est une discipline d'écriture — une logique de "
                "pensée, une structure et une séquence imposées — et non un "
                "habillage stylistique."),
            domain='writing',
            source='agents/createur.py:_TONE_DISCIPLINES',
            accepts_free_text=False,
        ),
        catalog=_TONE_DISCIPLINES,
        aliases=_TONE_ALIASES,
    )


def _emotion_skill() -> CatalogSkill:
    from agents.createur import (_EMOTION_DIRECTIVES, _normalize_emotion_key,
                                 _free_emotion_directive)
    return CatalogSkill(
        spec=SkillSpec(
            id='writing.emotion_directive',
            name="Directives d'émotion cible",
            description=(
                "Traduit l'émotion que l'audience doit ressentir en leviers "
                "d'écriture concrets. Accepte une émotion hors catalogue via un "
                "gabarit générique, la saisie étant alors neutralisée."),
            domain='writing',
            source='agents/createur.py:_EMOTION_DIRECTIVES',
            accepts_free_text=True,
        ),
        catalog=_EMOTION_DIRECTIVES,
        normalizer=_normalize_emotion_key,
        fallback=_free_emotion_directive,
    )


def register_all() -> None:
    registry.register(_tone_skill())
    registry.register(_emotion_skill())
