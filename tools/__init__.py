"""Catalogue des outils Gabriel.

Importer ce paquet suffit à peupler le registre : chaque module d'outils
s'y déclare à l'import.
"""

from tools.base import (  # noqa: F401
    FunctionTool, Tool, ToolError, ToolInput, ToolInputError, ToolSpec,
)
from tools.registry import (  # noqa: F401
    ToolNotAllowed, ToolNotFound, ToolRegistry, registry,
)

from tools import audience  # noqa: F401  (enregistre les outils d'audience)

__all__ = [
    "Tool", "ToolSpec", "ToolInput", "FunctionTool",
    "ToolError", "ToolInputError", "ToolNotFound", "ToolNotAllowed",
    "ToolRegistry", "registry",
]
