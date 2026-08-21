"""Outil de restitution — décrit la forme d'un résultat métier.

Le Design Agent ne doit pas laisser un LLM deviner la structure d'un résultat
à partir d'un dump JSON brut : c'est exactement le genre de calcul qui ne
doit jamais être délégué à un modèle (doctrine `tools/base.py`). Cet outil
fait le travail déterministe — compter, détecter les formes récurrentes,
détecter les paires de métriques — et ne rend que des faits, jamais un choix
de présentation. Le choix du format reste au planificateur (LLM), qui reçoit
ces faits plutôt que le JSON brut.
"""

from __future__ import annotations

from typing import Any

from tools.base import FunctionTool, ToolInput, ToolSpec
from tools.registry import registry


def _is_list_of_dicts(value: Any) -> bool:
    return isinstance(value, list) and bool(value) and all(isinstance(v, dict) for v in value)


def _numeric_keys(items: list[dict]) -> list[str]:
    """Clés présentes sur au moins la moitié des éléments avec une valeur
    numérique — signale une liste "scorée" (candidate à une matrice/graphe),
    pas une simple liste de textes."""
    if not items:
        return []
    counts: dict[str, int] = {}
    for item in items:
        for key, value in item.items():
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                counts[key] = counts.get(key, 0) + 1
    threshold = max(1, len(items) // 2)
    return sorted(key for key, count in counts.items() if count >= threshold)


def _describe_content_shape(envelope: dict) -> dict:
    source_agent = envelope.get("source_agent", "")
    content = envelope.get("content", {})
    if not isinstance(content, dict):
        content = {"value": content}

    fields = []
    for key, value in content.items():
        if _is_list_of_dicts(value):
            scored_on = _numeric_keys(value)
            fields.append({
                "key": key,
                "shape": "list_of_records",
                "count": len(value),
                "record_keys": sorted(value[0].keys()) if value else [],
                "scored_on": scored_on,
                "is_scored_list": len(scored_on) >= 2,
            })
        elif isinstance(value, list):
            fields.append({
                "key": key,
                "shape": "list_of_scalars",
                "count": len(value),
                "sample": [str(v) for v in value[:3]],
            })
        elif isinstance(value, dict):
            fields.append({
                "key": key,
                "shape": "object",
                "keys": sorted(value.keys()),
            })
        elif isinstance(value, (int, float)) and not isinstance(value, bool):
            fields.append({"key": key, "shape": "number", "value": value})
        else:
            text = str(value)
            fields.append({
                "key": key,
                "shape": "text",
                "length": len(text),
                "is_quote_like": len(text) < 240 and any(
                    marker in text for marker in ("«", "»", '"', "'")
                ),
            })

    return {
        "source_agent": source_agent,
        "field_count": len(fields),
        "fields": fields,
        # Signaux composites utiles au planificateur sans qu'il ait à les
        # redériver lui-même à partir de `fields`.
        "has_scored_list": any(f.get("is_scored_list") for f in fields),
        "has_quotes": any(f.get("is_quote_like") for f in fields),
        "has_multiple_records_lists": sum(
            1 for f in fields if f.get("shape") == "list_of_records"
        ) > 1,
    }


DESCRIBE_CONTENT_SHAPE = ToolSpec(
    id="design.describe_content_shape",
    name="Description de forme d'un résultat métier",
    description=(
        "Inspecte un résultat structuré (Psychologue, Stratège, Créateur, "
        "Cross-Analyse…) et rend des faits déterministes sur sa forme "
        "(listes scorées, citations, objets imbriqués) — jamais un choix de "
        "présentation, seulement la matière sur laquelle ce choix se base."),
    category="design",
    inputs=(
        ToolInput(
            "envelope",
            "Dict {source_agent: str, content: dict} — le résultat métier brut",
        ),
    ),
    output=(
        "{source_agent, field_count, fields: [...], has_scored_list: bool, "
        "has_quotes: bool, has_multiple_records_lists: bool}"
    ),
    deterministic=True,
    parallel_safe=True,
    cacheable=False,
    timeout_s=None,
)


def register_all() -> None:
    registry.register(FunctionTool(DESCRIBE_CONTENT_SHAPE, _describe_content_shape))


register_all()
