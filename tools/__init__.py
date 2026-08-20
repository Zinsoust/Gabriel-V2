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

from tools import audience    # noqa: F401  (enregistre les outils d'audience)
from tools import collection  # noqa: F401  (enregistre les outils de collecte)
from tools import files       # noqa: F401  (enregistre les outils de fichiers)
from tools import knowledge   # noqa: F401  (enregistre l'outil de recherche documentaire)
from tools import comparison  # noqa: F401  (enregistre l'outil de comparaison multi-sources)
from tools import nlp         # noqa: F401  (enregistre l'outil du pipeline NLP)
from tools import strategic_memory  # noqa: F401  (enregistre l'outil de mémoire stratégique)
from tools import statistics  # noqa: F401  (enregistre l'outil des livrables statistiques)
from tools import content_quality  # noqa: F401  (enregistre l'outil de contrôle qualité)

__all__ = [
    "Tool", "ToolSpec", "ToolInput", "FunctionTool",
    "ToolError", "ToolInputError", "ToolNotFound", "ToolNotAllowed",
    "ToolRegistry", "registry",
]
