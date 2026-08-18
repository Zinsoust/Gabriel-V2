"""Lecture du JSON produit par un LLM — implémentation unique.

PURPOSE
    Un modèle ne renvoie pas toujours du JSON valide : il l'entoure de prose,
    l'encadre de balises markdown, laisse une virgule finale ou tronque sa
    sortie. Quatre implémentations distinctes coexistaient pour gérer ça, avec
    **trois contrats d'échec incompatibles** — dont deux fonctions homonymes
    (`_parse_json`) dont l'une levait une exception là où l'autre renvoyait un
    objet marqué en erreur. Déplacer du code d'un agent à l'autre suffisait à
    introduire un bug silencieux.

RESPONSIBILITIES
    - nettoyer l'enrobage (balises markdown, prose autour de l'objet) ;
    - tenter plusieurs stratégies de réparation, de la plus stricte à la plus permissive ;
    - exposer explicitement le comportement en cas d'échec.

NON-RESPONSIBILITIES
    - ne valide aucun schéma métier (c'est au consommateur de le faire) ;
    - n'appelle aucun LLM ;
    - ne lit aucun fichier (voir services/file_importer pour les fichiers uploadés).

INPUTS   texte brut renvoyé par un modèle
OUTPUTS  dict — ou exception / objet sentinelle selon ``on_error``
"""

from __future__ import annotations

import json
import re

from json_repair import repair_json


_FENCE_OPEN = re.compile(r'^```(?:json)?\s*', re.MULTILINE)
_FENCE_CLOSE = re.compile(r'\s*```\s*$', re.MULTILINE)
_CONTROL_CHARS = re.compile(r'[\x00-\x08\x0b\x0c\x0e-\x1f]')
_TRAILING_COMMA = re.compile(r',\s*([}\]])')


def _strip_fences(text: str) -> str:
    """Retire un encadrement ```json … ``` s'il est présent."""
    return _FENCE_CLOSE.sub('', _FENCE_OPEN.sub('', text.strip()))


def _extract_object(text: str) -> str | None:
    """Isole le premier objet JSON d'un texte qui contient aussi de la prose."""
    start = text.find('{')
    if start == -1:
        return None
    end = text.rfind('}') + 1
    return text[start:end] if end > start else text[start:]


def _repair_to_dict(raw: str) -> dict:
    """``repair_json`` peut rendre une liste ou une chaîne : seul un dict convient."""
    result = repair_json(raw, return_objects=True)
    if isinstance(result, dict):
        return result
    raise ValueError(f"repair_json a retourné {type(result).__name__}, pas un dict")


# Du plus strict au plus permissif : on ne veut pas qu'une réparation agressive
# masque une sortie réellement cassée si un simple json.loads suffisait.
_STRATEGIES = (
    lambda raw: json.loads(raw),
    _repair_to_dict,
    lambda raw: json.loads(_TRAILING_COMMA.sub(r'\1', _CONTROL_CHARS.sub('', raw))),
    lambda raw: repair_json(raw, return_objects=True, skip_json_loads=True),
)


class AiJsonError(ValueError):
    """Le texte du modèle ne contient aucun objet JSON exploitable."""


def parse_ai_json(text, *, on_error: str = 'raise', label: str = ''):
    """Lit le JSON d'une réponse de modèle.

    ``on_error='raise'``     → lève ``AiJsonError`` (sites où un échec est fatal).
    ``on_error='sentinel'``  → renvoie ``{'raw': texte, 'parse_error': True}``
                               (sites qui préfèrent dégrader plutôt qu'échouer).

    ``label`` n'apparaît que dans le message d'erreur, pour situer l'appel.
    """
    if on_error not in ('raise', 'sentinel'):
        raise ValueError(f"on_error invalide : {on_error!r}")

    raw_text = text or ''
    candidates = []
    stripped = _strip_fences(raw_text)
    if stripped:
        candidates.append(stripped)
    # L'extraction d'accolades rattrape les réponses noyées dans de la prose ;
    # elle vient en second pour ne pas amputer un JSON déjà propre.
    extracted = _extract_object(stripped)
    if extracted and extracted != stripped:
        candidates.append(extracted)

    for candidate in candidates:
        for strategy in _STRATEGIES:
            try:
                result = strategy(candidate)
            except Exception:
                continue
            if isinstance(result, dict) and result:
                return result

    if on_error == 'sentinel':
        return {'raw': raw_text, 'parse_error': True}

    preview = raw_text[:120].replace('\n', ' ') or '(réponse vide)'
    where = f" [{label}]" if label else ''
    raise AiJsonError(f"Aucun JSON exploitable dans la réponse du modèle{where}. Début reçu : {preview}")
