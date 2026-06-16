# ─── Registre des agents Gabriel ─────────────────────────────────────────────
# Ce fichier garantit aussi que le répertoire racine du projet
# est toujours dans sys.path — peu importe d'où Python est lancé.

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
