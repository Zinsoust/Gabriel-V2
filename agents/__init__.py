# ─── Accès aux classes d'agents ──────────────────────────────────────────────
# Ce fichier n'est PAS le registre des agents : il expose les classes et
# garantit que la racine du projet est dans sys.path, peu importe d'où Python
# est lancé. Le registre — statuts réels, points d'entrée réels, outils et
# savoir-faire autorisés — vit dans agents/catalog.py.
#
# Il n'est volontairement pas importé ici : `agents.catalog` dépend des
# registres d'outils et de savoir-faire, qui dépendent eux-mêmes des agents.
# L'importer depuis ce fichier créerait un cycle.

import sys
import os

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

# ── Contrat et contexte partagé (toujours disponibles)
from agents.base    import AgentBase
from agents.context import AnalysisContext

# ── Agents — imports protégés individuellement
# Si un agent a une erreur, les autres restent disponibles

try:
    from agents.psychologue import Psychologue
except Exception as e:
    print(f"[GABRIEL] Impossible de charger Le Psychologue : {e}")
    Psychologue = None

try:
    from agents.stratege import Stratege
except Exception as e:
    print(f"[GABRIEL] Impossible de charger Le Stratège : {e}")
    Stratege = None

try:
    from agents.createur import Createur
except Exception as e:
    print(f"[GABRIEL] Impossible de charger Le Créateur : {e}")
    Createur = None

try:
    from agents.architecte import Architecte
except Exception as e:
    print(f"[GABRIEL] Impossible de charger L'Architecte : {e}")
    Architecte = None

__all__ = [
    'AgentBase',
    'AnalysisContext',
    'Psychologue',
    'Stratege',
    'Createur',
    'Architecte',
]
