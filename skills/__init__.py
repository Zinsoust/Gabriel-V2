"""Couche Skill : les savoir-faire méthodologiques de Gabriel."""

from skills.base import (CatalogSkill, Skill, SkillError, SkillFragment,
                         SkillSpec)
from skills.registry import SkillNotFound, SkillRegistry, registry

from tools import registry as _tool_registry  # noqa: E402
registry.configure(tool_registry=_tool_registry)

from skills import writing as _writing        # noqa: E402  (peuple le registre)
from skills import psychology as _psychology  # noqa: E402  (peuple le registre)
from skills import strategy as _strategy      # noqa: E402  (peuple le registre)

_writing.register_all()
_psychology.register_all()
_strategy.register_all()

__all__ = [
    'CatalogSkill', 'Skill', 'SkillError', 'SkillFragment', 'SkillSpec',
    'SkillNotFound', 'SkillRegistry', 'registry',
]
