# ═══════════════════════════════════════════════════════════════════════════
# CONTEXT BUILDER ARCHITECTURE — Question Planner (V1.1)
#
# Rôle unique : décider QUELLE dimension traiter ensuite. Ne génère aucun
# texte destiné à l'utilisateur (ça, c'est le rôle du Tone Renderer) et ne
# lit/écrit jamais la base directement (ça, c'est le rôle du Store / de
# l'Orchestrateur). Une fonction pure, facile à tester isolément.
# ═══════════════════════════════════════════════════════════════════════════

from typing import Optional
from agents.context_builder.schema import CONTEXT_DIMENSIONS, DIMENSION_BY_KEY


def dimension_status(dimension_key: str, filled_fields: dict) -> str:
    """'done' si tous les champs obligatoires de la dimension sont remplis,
    'in_progress' si certains le sont, 'not_started' sinon."""
    dim = DIMENSION_BY_KEY.get(dimension_key)
    if not dim:
        return 'not_started'
    required = [f['key'] for f in dim['fields'] if f['required']]
    if not required:
        return 'done'
    filled_count = sum(1 for k in required if (filled_fields.get(k) or '').strip())
    if filled_count == len(required):
        return 'done'
    if filled_count > 0:
        return 'in_progress'
    return 'not_started'


def progression(filled_fields: dict) -> list:
    """Vue de progression pour la Zone 3 — une entrée par dimension, dans
    l'ordre du brief, avec son statut. Alimente l'affichage ✓ / • / ○."""
    return [
        {
            'key':    d['key'],
            'label':  d['label'],
            'status': dimension_status(d['key'], filled_fields),
        }
        for d in CONTEXT_DIMENSIONS
    ]


def next_dimension(filled_fields: dict) -> Optional[dict]:
    """Retourne la prochaine dimension à traiter (la première, dans l'ordre du
    brief, qui n'a pas encore tous ses champs obligatoires remplis).
    None si toutes les dimensions obligatoires sont couvertes — le contexte
    est alors suffisant pour le Stratège."""
    for dim in CONTEXT_DIMENSIONS:
        if dimension_status(dim['key'], filled_fields) != 'done':
            return dim
    return None


def is_ready(filled_fields: dict) -> bool:
    """True si toutes les dimensions ont leurs champs obligatoires couverts."""
    return next_dimension(filled_fields) is None


def completion_ratio(filled_fields: dict) -> float:
    """Score global 0.0 → 1.0, basé sur les champs obligatoires toutes
    dimensions confondues — pour un indicateur simple type barre de
    progression globale, en plus de la vue par dimension."""
    from agents.context_builder.schema import REQUIRED_FIELD_KEYS
    if not REQUIRED_FIELD_KEYS:
        return 1.0
    filled_count = sum(1 for k in REQUIRED_FIELD_KEYS if (filled_fields.get(k) or '').strip())
    return round(filled_count / len(REQUIRED_FIELD_KEYS), 2)
