"""Couche Skill : les savoir-faire méthodologiques de Gabriel."""

from skills.base import (CatalogSkill, Skill, SkillError, SkillFragment,
                         SkillSpec)
from skills.registry import SkillNotFound, SkillRegistry, registry

from skills import writing as _writing  # noqa: E402  (peuple le registre)

_writing.register_all()

__all__ = [
    'CatalogSkill', 'Skill', 'SkillError', 'SkillFragment', 'SkillSpec',
    'SkillNotFound', 'SkillRegistry', 'registry',
]
