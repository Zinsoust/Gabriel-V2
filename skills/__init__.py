"""Couche Skill : les savoir-faire méthodologiques de Gabriel."""

from skills.base import (CatalogSkill, Skill, SkillError, SkillFragment,
                         SkillSpec)
from skills.registry import SkillNotFound, SkillRegistry, registry

from tools import registry as _tool_registry  # noqa: E402
registry.configure(tool_registry=_tool_registry)

from skills import writing as _writing        # noqa: E402  (peuple le registre)
from skills import psychology as _psychology  # noqa: E402  (peuple le registre)
from skills import strategy as _strategy      # noqa: E402  (peuple le registre)
from skills import strategy_corpus as _strategy_corpus  # noqa: E402
from skills import human_voice as _human_voice          # noqa: E402

_writing.register_all()
_psychology.register_all()
_strategy.register_all()
_strategy_corpus.register_all()
_human_voice.register_all()

__all__ = [
    'CatalogSkill', 'Skill', 'SkillError', 'SkillFragment', 'SkillSpec',
    'SkillNotFound', 'SkillRegistry', 'registry',
]
