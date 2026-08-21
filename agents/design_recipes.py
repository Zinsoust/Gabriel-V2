"""Recettes de restitution — validées une fois, servies ensuite sans latence.

Décision retenue face à la question de la latence : pas de critique en direct
par requête utilisateur (ça suppose un navigateur automatisé + un modèle
vision, que Gabriel n'a pas, et ça coûterait plusieurs secondes à chaque
affichage). À la place, une recette (forme de contenu → composants Gabriel +
mapping des champs) est validée une bonne fois hors ligne, puis reconnue ici
par une correspondance purement déterministe — aucun appel LLM dans ce
fichier.

Si aucune recette ne correspond, `match_recipe` rend `None` : le Design Agent
dégrade alors vers un conteneur générique déjà approuvé et journalise le
manque dans `data/design_recipe_gaps.json`, pour que l'équipe (mode
DESIGN_DEVELOPMENT) construise et valide la recette manquante hors ligne —
jamais l'utilisateur qui attend qu'un format soit inventé en direct.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any, Callable, Optional

_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_GAPS_FILE = os.path.join(_BASE_DIR, 'data', 'design_recipe_gaps.json')

# Composant de repli : un cadre générique déjà approuvé (DESIGN.md, §5), jamais
# un affichage inventé. Sert quand aucune recette validée ne correspond.
FALLBACK_COMPONENT = "premium_card_frame"


def _list_of_records_fields(shape: dict) -> list[dict]:
    return [f for f in shape.get("fields", []) if f.get("shape") == "list_of_records"]


def _number_fields(shape: dict) -> list[dict]:
    return [f for f in shape.get("fields", []) if f.get("shape") == "number"]


# ── Recette 1 : liste de records textuels (titre + détails), non notée ──────
# Validée sur le plan d'action réel du Stratège (`agents/stratege.py`,
# action_plan_immediat : action/signal_source/impact/delai — texte libre).

def _match_editorial_list(shape: dict) -> bool:
    records = _list_of_records_fields(shape)
    if len(records) != 1:
        return False
    field = records[0]
    return not field.get("is_scored_list") and len(field.get("record_keys", [])) >= 3


def _build_editorial_list(shape: dict, envelope: dict) -> dict:
    field = _list_of_records_fields(shape)[0]
    keys = field["record_keys"]
    mapping = {keys[0]: "titre"}
    for key in keys[1:]:
        mapping[key] = "détail (sous-titre / corps, dans l'ordre du champ)"
    return {
        "format_choice": "liste éditoriale ordonnée",
        "components_used": ["editorial_numbered_list"],
        "field_mapping": {field["key"]: mapping},
        "missing_components": [],
        "justification": (
            "Recette validée : liste de records textuels non notée → liste "
            "éditoriale numérotée, sans latence de composition."),
        "recipe_id": "editorial_list_v1",
    }


# ── Recette 2 : paire de scores de confiance ────────────────────────────────
# Validée sur le couple réel confidence_score / confidence_score_independant
# (agents/stratege.py) — DESIGN.md, §5 : "toujours affichées en paire quand
# les deux scores existent".

def _match_confidence_pair(shape: dict) -> bool:
    numbers = _number_fields(shape)
    if len(numbers) != 2:
        return False
    return all("confian" in f["key"].lower() or "confidence" in f["key"].lower()
                for f in numbers)


def _build_confidence_pair(shape: dict, envelope: dict) -> dict:
    numbers = _number_fields(shape)
    numbers_sorted = sorted(numbers, key=lambda f: f["key"])
    return {
        "format_choice": "jauges de confiance en paire",
        "components_used": ["confidence_gauge"],
        "field_mapping": {
            numbers_sorted[0]["key"]: "jauge --ok",
            numbers_sorted[1]["key"]: "jauge --risk",
        },
        "missing_components": [],
        "justification": (
            "Recette validée : deux scores de confiance comparables → paire "
            "de jauges (DESIGN.md §5), sans latence de composition."),
        "recipe_id": "confidence_pair_v1",
    }


# Ordre = ordre de priorité de correspondance.
_RECIPES: tuple[tuple[str, Callable[[dict], bool], Callable[[dict, dict], dict]], ...] = (
    ("confidence_pair_v1", _match_confidence_pair, _build_confidence_pair),
    ("editorial_list_v1", _match_editorial_list, _build_editorial_list),
)


def match_recipe(shape: dict, envelope: dict) -> Optional[dict]:
    """Rend la décision d'une recette validée si sa forme correspond, sinon None."""
    for _recipe_id, matches, build in _RECIPES:
        if matches(shape):
            return build(shape, envelope)
    return None


def _signature(shape: dict) -> str:
    """Résumé compact et stable de la forme — sert seulement à dédupliquer la
    file d'attente des manques, pas à choisir un format."""
    parts = []
    for field in shape.get("fields", []):
        parts.append(f"{field['key']}:{field['shape']}:{field.get('is_scored_list', False)}")
    return "|".join(sorted(parts))


def log_gap(shape: dict, envelope: dict) -> None:
    """Journalise un besoin non couvert par le catalogue de recettes actuel.

    Fichier plat JSON (`data/*.json`), même mécanisme que
    `core/business_context.py` — pas de nouveau système de mémoire parallèle.
    Dédupliqué par signature : un même manque répété ne pollue pas la file.
    """
    os.makedirs(os.path.dirname(_GAPS_FILE), exist_ok=True)
    try:
        with open(_GAPS_FILE, 'r', encoding='utf-8') as handle:
            gaps = json.load(handle)
    except (FileNotFoundError, json.JSONDecodeError):
        gaps = []

    signature = _signature(shape)
    if any(g.get("signature") == signature for g in gaps):
        return

    gaps.append({
        "signature": signature,
        "source_agent": shape.get("source_agent", ""),
        "fields": shape.get("fields", []),
        "has_scored_list": shape.get("has_scored_list", False),
        "seen_at": datetime.now(timezone.utc).isoformat(),
        # Gardé pour `scripts/design_review_gaps.py` : la forme seule ne
        # suffit pas à fabriquer une recette (valeurs réelles nécessaires
        # pour un `field_mapping` sensé). Revue humaine hors ligne uniquement.
        "example_envelope": envelope,
    })
    with open(_GAPS_FILE, 'w', encoding='utf-8') as handle:
        json.dump(gaps, handle, ensure_ascii=False, indent=2)
