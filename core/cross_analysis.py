"""Contrats de données pour la Cross Analyse du Psychologue.

Cette couche ne remplace pas ``core.analyzer.analyze_comments``. Elle prépare
et relie plusieurs analyses individuelles en conservant la provenance de
chaque signal. Le calcul des convergences est volontairement déterministe et
équilibré par source : l'interprétation psychologique reste une responsabilité
du LLM, dans une étape ultérieure.
"""

from __future__ import annotations

import math
import re
import uuid
from typing import Any, Dict, Iterable, List, Mapping, Sequence

from services.scraper import extract_youtube_id


SOURCE_ANALYSIS_SCHEMA_VERSION = "1.0"
CROSS_ANALYSIS_SCHEMA_VERSION = "1.0"
SOURCE_PIPELINE_VERSION = "simple-psychologue-v1"
DATA_QUALITY_THRESHOLDS = {
    "insufficient": 10,
    "exploratory": 30,
    "moderate": 80,
}
MIN_CROSS_SOURCES = 2
MAX_CROSS_SOURCES = 5
DEFAULT_CROSS_OPTIONS = {
    "refresh": False,
    "include_replies": False,
    "max_comments_per_source": 150,
    "max_parallel_sources": 1,
}


class CrossAnalysisValidationError(ValueError):
    """Erreur de contrat explicite, sûre à retourner au client."""


def _clean_text(value: Any, limit: int = 2000) -> str:
    return str(value or "").strip()[:limit]


def _slug(value: Any) -> str:
    value = _clean_text(value, 160).lower()
    value = re.sub(r"[^a-z0-9_-]+", "-", value)
    return value.strip("-")


def _source_id() -> str:
    """Identifiant interne, unique pour préserver la provenance d'une session."""
    return f"src_{uuid.uuid4().hex[:16]}"


def _normalise_platform(value: Any) -> str:
    platform = _clean_text(value, 32).lower()
    aliases = {"youtube.com": "youtube", "youtu.be": "youtube"}
    return aliases.get(platform, platform or "youtube")


def normalize_cross_sources(
    raw_sources: Any,
    *,
    min_sources: int = MIN_CROSS_SOURCES,
    max_sources: int = MAX_CROSS_SOURCES,
) -> List[Dict[str, Any]]:
    """Valide et normalise les sources d'une demande de Cross Analyse.

    V1 reçoit uniquement des vidéos YouTube. Le contrat porte déjà un champ
    ``platform`` et ne dépend pas de ``video_a`` / ``video_b`` : ajouter une
    plateforme sera donc une extension contrôlée, pas une refonte.
    """
    if not isinstance(raw_sources, list):
        raise CrossAnalysisValidationError("Le champ 'sources' doit être une liste.")
    if not min_sources <= len(raw_sources) <= max_sources:
        raise CrossAnalysisValidationError(
            f"La Cross Analyse requiert entre {min_sources} et {max_sources} sources."
        )

    normalized: List[Dict[str, Any]] = []
    seen_external_ids = set()

    for index, raw_source in enumerate(raw_sources):
        if not isinstance(raw_source, Mapping):
            raise CrossAnalysisValidationError(
                f"La source {index + 1} doit être un objet contenant une URL YouTube."
            )

        platform = _normalise_platform(raw_source.get("platform") or raw_source.get("source"))
        url = _clean_text(raw_source.get("url") or raw_source.get("content"), 2048)
        if platform != "youtube":
            raise CrossAnalysisValidationError(
                f"La plateforme '{platform or 'inconnue'}' n'est pas encore prise en charge "
                "par la Cross Analyse."
            )
        if not url:
            raise CrossAnalysisValidationError(f"L'URL de la source {index + 1} est requise.")

        video_id = extract_youtube_id(url)
        if not video_id:
            raise CrossAnalysisValidationError(
                f"La source {index + 1} n'est pas une URL de vidéo YouTube valide."
            )
        if video_id in seen_external_ids:
            raise CrossAnalysisValidationError(
                "Une même vidéo YouTube ne peut figurer qu'une fois dans une Cross Analyse."
            )
        seen_external_ids.add(video_id)

        label = _clean_text(raw_source.get("label"), 140) or f"Vidéo {index + 1}"
        normalized.append({
            "source_id": _source_id(),
            "position": index,
            "platform": "youtube",
            "source_type": "youtube",
            "external_id": video_id,
            "video_id": video_id,
            "input_url": url,
            "canonical_url": f"https://www.youtube.com/watch?v={video_id}",
            "label": label,
            "metadata": {},
        })

    return normalized


def normalize_cross_options(raw_options: Any) -> Dict[str, Any]:
    """Normalise les options Cross sans affecter les options de l'analyse simple."""
    if raw_options is None:
        raw_options = {}
    if not isinstance(raw_options, Mapping):
        raise CrossAnalysisValidationError("Le champ 'options' doit être un objet.")

    def _bool(name: str) -> bool:
        """Accepte aussi les booléens issus d'un formulaire HTML.

        ``bool('false')`` vaut True en Python : sans cette normalisation, une
        option explicitement désactivée pouvait être interprétée à l'inverse.
        """
        value = raw_options.get(name, DEFAULT_CROSS_OPTIONS[name])
        if isinstance(value, str):
            normalized = value.strip().lower()
            if normalized in {"true", "1", "yes", "on"}:
                return True
            if normalized in {"false", "0", "no", "off", ""}:
                return False
        return bool(value)

    try:
        max_comments = int(raw_options.get(
            "max_comments_per_source", DEFAULT_CROSS_OPTIONS["max_comments_per_source"]
        ))
    except (TypeError, ValueError):
        raise CrossAnalysisValidationError("max_comments_per_source doit être un nombre entier.")
    if not 10 <= max_comments <= 200:
        raise CrossAnalysisValidationError(
            "max_comments_per_source doit être compris entre 10 et 200 dans la version actuelle."
        )

    try:
        max_parallel = int(raw_options.get(
            "max_parallel_sources", DEFAULT_CROSS_OPTIONS["max_parallel_sources"]
        ))
    except (TypeError, ValueError):
        raise CrossAnalysisValidationError("max_parallel_sources doit être un nombre entier.")
    # run_psycho ouvre déjà un pool de tâches LLM : deux sources sont la limite
    # sûre pour Render et les limites actuelles du provider.
    max_parallel = max(1, min(max_parallel, 2))

    if _bool("include_replies"):
        raise CrossAnalysisValidationError(
            "La collecte des réponses YouTube sera disponible dans une prochaine version ; "
            "utilisez include_replies=false pour le moment."
        )

    return {
        "refresh": _bool("refresh"),
        "include_replies": False,
        "max_comments_per_source": max_comments,
        "max_parallel_sources": max_parallel,
    }


def attach_source_metadata(
    source: Mapping[str, Any],
    video_metadata: Mapping[str, Any] | None = None,
) -> Dict[str, Any]:
    """Ajoute les métadonnées récupérées sans modifier l'identité de la source."""
    result = dict(source)
    metadata = dict(result.get("metadata") or {})
    for key in ("title", "channel", "description", "published_at", "thumbnail_url"):
        value = (video_metadata or {}).get(key)
        if value not in (None, ""):
            metadata[key] = _clean_text(value, 1200 if key == "description" else 400)
    # Champs numériques : jamais passés par _clean_text (qui les transformerait
    # en texte). like_count reste None si l'API ne l'a pas renvoyé (compteur
    # masqué par le créateur) — distinct de 0 like réel.
    source_metadata = video_metadata or {}
    for key in ("view_count", "comment_count"):
        value = source_metadata.get(key)
        if isinstance(value, int):
            metadata[key] = value
    if "like_count" in source_metadata:
        metadata["like_count"] = source_metadata["like_count"]
    duration = source_metadata.get("duration")
    if duration:
        metadata["duration"] = _clean_text(duration, 40)
    result["metadata"] = metadata
    return result


def with_comment_provenance(
    comments: Iterable[Mapping[str, Any]], source: Mapping[str, Any]
) -> List[Dict[str, Any]]:
    """Retourne les commentaires enrichis, sans écraser leurs données existantes.

    Une déduplication future pourra marquer des doublons, mais ne doit jamais
    retirer le rattachement à la vidéo d'origine. Cette fonction est donc la
    frontière de provenance utilisée avant tout calcul multi-source.
    """
    source_id = _clean_text(source.get("source_id"), 80)
    if not source_id:
        raise CrossAnalysisValidationError("Chaque commentaire Cross Analyse requiert un source_id.")

    source_type = _clean_text(source.get("source_type") or source.get("platform"), 32)
    external_id = _clean_text(source.get("external_id") or source.get("video_id"), 160)
    enriched: List[Dict[str, Any]] = []

    for position, original in enumerate(comments):
        if not isinstance(original, Mapping):
            continue
        text = _clean_text(original.get("text"), 10000)
        if not text:
            continue

        row = dict(original)
        external_comment_id = _clean_text(
            original.get("external_comment_id") or original.get("comment_id") or original.get("id"),
            180,
        )
        # Certaines APIs ne fournissent pas d'identifiant stable. Le fallback
        # est volontairement unique à cette source et conservé comme tel.
        comment_id = _clean_text(original.get("comment_id"), 220)
        if not comment_id or comment_id == external_comment_id:
            suffix = external_comment_id or f"row-{position}"
            comment_id = f"{source_id}:{suffix}"

        inherited_metadata = original.get("metadata")
        metadata = dict(inherited_metadata) if isinstance(inherited_metadata, Mapping) else {}
        for key in ("published_at", "updated_at", "reply_count"):
            if original.get(key) not in (None, ""):
                metadata[key] = original.get(key)

        row.update({
            "comment_id": comment_id,
            "external_comment_id": external_comment_id,
            "source_id": source_id,
            "source_type": source_type,
            "source": source_type,
            "video_id": external_id if source_type == "youtube" else row.get("video_id", ""),
            "text": text,
            "metadata": metadata,
        })
        enriched.append(row)

    return enriched


def clean_and_deduplicate_source_comments(
    comments: Iterable[Mapping[str, Any]], source: Mapping[str, Any]
) -> Dict[str, Any]:
    """Prépare un corpus source sans perdre les commentaires bruts.

    La déduplication est volontairement limitée aux doublons textuels exacts
    normalisés (casse et espaces). Les quasi-doublons demandent une couche
    sémantique dédiée ; les supprimer ici risquerait de confondre répétition
    réelle et spam. Le texte original est conservé dans ``raw_comments``.
    """
    raw_comments = with_comment_provenance(comments, source)
    retained_comments: List[Dict[str, Any]] = []
    seen_texts = set()
    duplicates_removed = 0

    for row in raw_comments:
        normalized_text = re.sub(r"\s+", " ", row.get("text", "").strip().casefold())
        row["normalized_text"] = normalized_text
        if not normalized_text:
            continue
        if normalized_text in seen_texts:
            duplicates_removed += 1
            row["is_exact_duplicate"] = True
            continue
        seen_texts.add(normalized_text)
        row["is_exact_duplicate"] = False
        retained_comments.append(row)

    return {
        "raw_comments": raw_comments,
        "retained_comments": retained_comments,
        "dataset": {
            "comments_collected": len(raw_comments),
            "comments_retained": len(retained_comments),
            "duplicates_removed": duplicates_removed,
            "deduplication_status": "exact_text_normalized",
        },
    }


def _as_signal_items(value: Any) -> List[Dict[str, Any]]:
    """Convertit les formes historiques (liste, dict, str) en signaux stables."""
    if value is None:
        return []
    if isinstance(value, str):
        label = _clean_text(value, 240)
        return [{"label": label, "weight": 1.0}] if label else []
    if isinstance(value, Mapping):
        items = []
        for label, raw_weight in value.items():
            if isinstance(raw_weight, Mapping):
                weight = raw_weight.get("pct", raw_weight.get("score", raw_weight.get("count", 1)))
                display = raw_weight.get("label", label)
            else:
                weight, display = raw_weight, label
            try:
                weight = float(weight)
            except (TypeError, ValueError):
                weight = 1.0
            display = _clean_text(display, 240)
            if display:
                items.append({"label": display, "weight": max(weight, 0.0)})
        return items
    if isinstance(value, Sequence):
        items = []
        for entry in value:
            if isinstance(entry, Mapping):
                label = _clean_text(
                    entry.get("label") or entry.get("name") or entry.get("theme")
                    or entry.get("emotion") or entry.get("signal") or entry.get("mot")
                    or entry.get("text"),
                    240,
                )
                weight = entry.get(
                    "pct", entry.get("pourcentage", entry.get("score", entry.get("count", 1)))
                )
                try:
                    weight = float(weight)
                except (TypeError, ValueError):
                    weight = 1.0
            else:
                label, weight = _clean_text(entry, 240), 1.0
            if label:
                items.append({"label": label, "weight": max(weight, 0.0)})
        return items
    return []


def _signal_values(source_analysis: Mapping[str, Any], category: str) -> List[Dict[str, Any]]:
    """Lit les nouvelles clés et les formes du dashboard actuel sans les dupliquer."""
    direct = source_analysis.get(category)
    if category == "emotions" and isinstance(direct, Mapping):
        # Dans le résultat individuel actuel, ``emotions`` est un objet riche
        # (repartition, dominante, intensite, commentaires_revelateurs, ...) —
        # la distribution comparable vit sous 'repartition', pas au niveau
        # racine. Même piège déjà traité pour 'aspirations' plus bas dans ce
        # fichier : sans cette extraction, les noms de champs eux-mêmes
        # ("dominante", "intensite"...) sont pris pour des émotions détectées.
        direct = direct.get("repartition")
    if direct:
        return _as_signal_items(direct)

    dashboard = source_analysis.get("dashboard") or {}
    if not isinstance(dashboard, Mapping):
        dashboard = {}
    legacy_keys = {
        "emotions": "emotion_distribution",
        "themes": "sujets_recurrents",
        "behavioral_signals": "signal_distribution",
    }
    legacy = dashboard.get(legacy_keys.get(category, category))
    values = _as_signal_items(legacy)
    if values:
        return values

    # Les valeurs dominantes sont également utiles lorsqu'aucune distribution
    # complète n'est disponible, mais elles ne remplacent pas les chiffres.
    dominant_key = {
        "emotions": "dominant_emotion",
        "beliefs": "dominant_stance",
    }.get(category)
    return _as_signal_items(dashboard.get(dominant_key)) if dominant_key else []


def _path_value(payload: Mapping[str, Any], *path: str) -> Any:
    current: Any = payload
    for key in path:
        if not isinstance(current, Mapping):
            return None
        current = current.get(key)
    return current


def _merge_signal_lists(*values: Any) -> List[Dict[str, Any]]:
    """Normalise des listes LLM hétérogènes tout en évitant les doublons exacts."""
    merged: List[Dict[str, Any]] = []
    seen = set()
    for value in values:
        for item in _as_signal_items(value):
            key = _slug(item.get("label"))
            if not key or key in seen:
                continue
            seen.add(key)
            merged.append(item)
    return merged


def _data_quality(comment_count: int, confidence_score: Any, noise_ratio: Any) -> Dict[str, Any]:
    """Expose une qualité lisible, sans la présenter comme une vérité scientifique."""
    try:
        confidence = float(confidence_score or 0)
    except (TypeError, ValueError):
        confidence = 0.0
    if confidence > 1:
        confidence /= 100
    try:
        noise = float(noise_ratio or 0)
    except (TypeError, ValueError):
        noise = 0.0

    if comment_count < DATA_QUALITY_THRESHOLDS["insufficient"]:
        level = "insufficient"
    elif comment_count < DATA_QUALITY_THRESHOLDS["exploratory"]:
        level = "exploratory"
    elif comment_count < DATA_QUALITY_THRESHOLDS["moderate"]:
        level = "moderate"
    else:
        level = "strong"

    warnings = []
    if comment_count < DATA_QUALITY_THRESHOLDS["exploratory"]:
        warnings.append("Volume de commentaires limité : lecture exploratoire.")
    if confidence and confidence < 0.45:
        warnings.append("Cohérence des signaux limitée.")
    if noise >= 35:
        warnings.append("Part importante de bruit ou de commentaires très courts.")
    return {
        "level": level,
        "comment_count": comment_count,
        "confidence_score": round(confidence, 2),
        "noise_ratio": round(noise, 1),
        "warnings": warnings,
        "method": "volume_plus_signaux_existants",
    }


def build_source_analysis(
    source: Mapping[str, Any],
    result: Mapping[str, Any],
    comments: Iterable[Mapping[str, Any]],
    dataset: Mapping[str, Any] | None = None,
) -> Dict[str, Any]:
    """Adapte une sortie *existante* de ``run_psycho`` au contrat par source.

    ``result`` reste inchangé et peut toujours alimenter l'interface actuelle.
    Le nouvel objet est un read-model stable pour la Cross Analyse.
    """
    dashboard = dict(result.get("dashboard") or {})
    meta = dict(result.get("meta") or {})
    psychology = dict(result.get("psychologie") or {})
    aspirations_data = dict(result.get("aspirations") or {})
    marketing = dict(result.get("marketing") or {})
    interpretation = dict(result.get("interpretation") or {})
    comment_rows = list(comments)
    comment_count = int(meta.get("total_commentaires") or len(comment_rows))
    qualified_count = int(meta.get("commentaires_analyses") or comment_count)
    dashboard_qualified = int(dashboard.get("qualified_comments") or qualified_count)
    confidence_score = dashboard.get("confidence_score", meta.get("confidence_score", 0))
    noise_ratio = dashboard.get("noise_ratio", meta.get("noise_ratio", 0))

    evidence = []
    for row in comment_rows:
        text = _clean_text(row.get("text"), 500)
        if text:
            evidence.append({
                "comment_id": row.get("comment_id", ""),
                "source_id": row.get("source_id", source.get("source_id", "")),
                "video_id": row.get("video_id", source.get("video_id", "")),
                "text": text,
                "likes": row.get("likes", 0),
                "metadata": dict(row.get("metadata") or {}),
            })

    fears = _merge_signal_lists(
        interpretation.get("peurs"), psychology.get("peurs_implicites"), result.get("fears"),
    )
    motivations = _merge_signal_lists(
        interpretation.get("motivations"), psychology.get("motivations_profondes"), result.get("motivations"),
    )
    frustrations = _merge_signal_lists(
        interpretation.get("frustrations"), psychology.get("frustrations"), result.get("frustrations"),
    )
    beliefs = _merge_signal_lists(
        interpretation.get("croyances_limitantes"), interpretation.get("croyances_mobilisatrices"),
        psychology.get("croyances_limitantes"), psychology.get("croyances_mobilisatrices"),
        result.get("beliefs"),
    )
    objections = _merge_signal_lists(
        interpretation.get("objections"), marketing.get("objections_visibles"),
        marketing.get("objections_invisibles"), result.get("objections"),
    )
    direct_aspirations = result.get("aspirations")
    # Dans le résultat actuel, ``aspirations`` est un objet riche avec des
    # phrases et des champs narratifs. On n'en fait pas une liste de labels :
    # seuls ses signaux explicitement listés (ambitions) sont comparables.
    if isinstance(direct_aspirations, Mapping):
        direct_aspirations = None
    aspirations = _merge_signal_lists(
        interpretation.get("desirs"), psychology.get("desirs_caches"),
        aspirations_data.get("ambitions"), direct_aspirations,
    )
    metadata = {
        "video_id": source.get("video_id", source.get("external_id", "")),
        "canonical_url": source.get("canonical_url", ""),
        **dict(source.get("metadata") or {}),
    }

    dataset_summary = {
        "comments_collected": len(comment_rows),
        "comments_retained": comment_count,
        "comments_qualified": dashboard_qualified,
        "comments_sent_to_llm": qualified_count,
        "duplicates_removed": None,
        "deduplication_status": "not_applied",
    }
    if isinstance(dataset, Mapping):
        dataset_summary.update({
            key: dataset[key] for key in (
                "comments_collected", "comments_retained", "duplicates_removed", "deduplication_status"
            ) if key in dataset
        })

    return {
        "schema_version": SOURCE_ANALYSIS_SCHEMA_VERSION,
        "pipeline_version": SOURCE_PIPELINE_VERSION,
        "source_id": source.get("source_id", ""),
        "platform": source.get("platform", source.get("source_type", "")),
        # video_metadata est conservé pour la première fondation Cross ;
        # metadata est le nom normalisé destiné aux prochains consommateurs.
        "metadata": metadata,
        "video_metadata": metadata,
        "dataset": dataset_summary,
        "comment_stats": {
            "total_comments": comment_count,
            "qualified_comments": qualified_count,
            "confidence_score": confidence_score,
            "noise_ratio": noise_ratio,
        },
        "data_quality": _data_quality(comment_count, confidence_score, noise_ratio),
        "dashboard": dashboard,
        "kpis": dict(result.get("kpis") or {}),
        "themes": _signal_values(result, "themes"),
        "emotions": _signal_values(result, "emotions"),
        "fears": fears,
        "aspirations": aspirations,
        "frustrations": frustrations,
        "beliefs": beliefs,
        "motivations": motivations,
        "objections": objections,
        "behavioral_signals": _signal_values(result, "behavioral_signals"),
        "personas": list(result.get("personas") or []),
        "psychological_summary": dict(result.get("interpretation") or {}),
        "evidence": evidence,
        "analysis_id": result.get("analysis_id", ""),
    }


def _source_signal_map(source_analysis: Mapping[str, Any], category: str) -> Dict[str, Dict[str, Any]]:
    # Une source apporte au plus une voix par signal : c'est ce qui empêche une
    # audience de 150 commentaires d'écraser une audience de 30 commentaires.
    signals: Dict[str, Dict[str, Any]] = {}
    for item in _signal_values(source_analysis, category):
        label = _clean_text(item.get("label"), 240)
        key = _slug(label)
        if not key:
            continue
        candidate = {"label": label, "weight": float(item.get("weight", 1.0) or 0.0)}
        if key not in signals or candidate["weight"] > signals[key]["weight"]:
            signals[key] = candidate
    return signals


def _cross_signals(source_analyses: Sequence[Mapping[str, Any]], category: str) -> Dict[str, Any]:
    presence: Dict[str, List[Dict[str, Any]]] = {}
    total_sources = len(source_analyses)
    for source in source_analyses:
        source_id = _clean_text(source.get("source_id"), 80)
        for key, signal in _source_signal_map(source, category).items():
            presence.setdefault(key, []).append({
                "source_id": source_id,
                "label": signal["label"],
                "weight": round(signal["weight"], 3),
            })

    threshold = max(2, math.ceil(total_sources * 0.6))
    convergences, specific, divergences = [], [], []
    source_ids = [_clean_text(source.get("source_id"), 80) for source in source_analyses]
    for rows in presence.values():
        coverage = len(rows)
        weights_by_source = {row["source_id"]: row["weight"] for row in rows}
        complete_weights = [weights_by_source.get(source_id, 0.0) for source_id in source_ids]
        intensity_range = round(max(complete_weights, default=0) - min(complete_weights, default=0), 3)
        item = {
            "label": rows[0]["label"],
            "sources_count": coverage,
            "source_coverage": round(coverage / max(total_sources, 1), 3),
            "sources": rows,
            "intensity_range": intensity_range,
        }
        if coverage >= threshold:
            convergences.append(item)
        elif coverage == 1:
            specific.append(item)
        # Une divergence est une différence de fréquence/intensité observable,
        # pas une contradiction psychologique déduite par le code. Les poids
        # issus de distributions sont en %, donc 25 points est un seuil lisible.
        if coverage >= 2 and intensity_range >= 25:
            divergences.append(item)

    sorter = lambda item: (-item["sources_count"], item["label"].lower())
    return {
        "convergences": sorted(convergences, key=sorter),
        "divergences": sorted(divergences, key=lambda item: (-item["intensity_range"], item["label"].lower())),
        "source_specific": sorted(specific, key=sorter),
        "all_signals": sorted(
            [{"label": rows[0]["label"], "sources_count": len(rows), "sources": rows}
             for rows in presence.values()],
            key=sorter,
        ),
    }


def _detect_stance_oppositions(source_analyses: Sequence[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    """Détecte les oppositions de position mesurées entre audiences."""
    def _weight(value: Any) -> float:
        try:
            return float(value or 0)
        except (TypeError, ValueError):
            return 0.0

    positions = []
    for source in source_analyses:
        dashboard = source.get("dashboard") or {}
        distribution = dashboard.get("stance_distribution") if isinstance(dashboard, Mapping) else {}
        if not isinstance(distribution, Mapping) or not distribution:
            continue
        dominant, pct = max(distribution.items(), key=lambda item: _weight(item[1]))
        positions.append({
            "source_id": source.get("source_id", ""),
            "position": dominant,
            "pct": round(_weight(pct), 1),
        })

    favorable = [row for row in positions if row["position"] == "favorable" and row["pct"] >= 30]
    opposed = [row for row in positions if row["position"] == "oppose" and row["pct"] >= 30]
    if favorable and opposed:
        return [{
            "type": "stance_opposition",
            "observation": "Des sources présentent des positions dominantes favorables et opposées.",
            "source_positions": positions,
            "interpretation_status": "pending_llm",
        }]
    return []


def _signal_insight_id(category: str, label: str) -> str:
    return f"cross:{_slug(category)}:{_slug(label)}"


def _representative_source_evidence(
    source_analyses: Sequence[Mapping[str, Any]], signal_sources: Sequence[Mapping[str, Any]],
) -> List[Dict[str, Any]]:
    """Retourne des extraits traçables par source, sans prétendre les lier au signal.

    L'analyse simple actuelle ne produit pas encore de lien signal→commentaire.
    Nous exposons donc ces extraits comme preuves *de source représentatives*,
    et non comme justification causale du signal. C'est une frontière
    importante pour éviter une fausse précision dans le dashboard Cross.
    """
    wanted = {str(item.get("source_id") or "") for item in signal_sources}
    rows: List[Dict[str, Any]] = []
    for source in source_analyses:
        source_id = str(source.get("source_id") or "")
        if source_id not in wanted:
            continue
        evidence = [item for item in (source.get("evidence") or []) if isinstance(item, Mapping)]
        evidence.sort(key=lambda item: item.get("likes", 0) or 0, reverse=True)
        rows.append({
            "source_id": source_id,
            "video_id": (source.get("metadata") or {}).get("video_id", source.get("video_id", "")),
            "evidence_kind": "representative_source_comments_not_signal_attribution",
            "comments": [
                {
                    "comment_id": item.get("comment_id", ""),
                    "source_id": item.get("source_id", source_id),
                    "video_id": item.get("video_id", ""),
                    "text": _clean_text(item.get("text"), 500),
                    "likes": item.get("likes", 0),
                }
                for item in evidence[:3]
            ],
        })
    return rows


def _cross_quality(source_analyses: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    levels = [
        str((source.get("data_quality") or {}).get("level") or "insufficient")
        for source in source_analyses
    ]
    ranking = {"insufficient": 0, "exploratory": 1, "moderate": 2, "strong": 3}
    minimum = min(levels, key=lambda level: ranking.get(level, 0)) if levels else "insufficient"
    return {
        "level": minimum,
        "per_source": [
            {"source_id": source.get("source_id", ""), "level": level}
            for source, level in zip(source_analyses, levels)
        ],
        "method": "minimum_source_quality",
    }


def build_cross_analysis(source_analyses: Sequence[Mapping[str, Any]]) -> Dict[str, Any]:
    """Construit la partie mesurable de la Cross Analyse.

    Cette fonction ne produit aucune interprétation psychologique générative.
    Elle compte, compare et conserve la preuve par source ; un LLM pourra
    ensuite recevoir cet evidence pack pour formuler une conclusion nuancée.
    """
    if not isinstance(source_analyses, Sequence) or isinstance(source_analyses, (str, bytes)):
        raise CrossAnalysisValidationError("Les analyses source doivent être une liste.")
    if not MIN_CROSS_SOURCES <= len(source_analyses) <= MAX_CROSS_SOURCES:
        raise CrossAnalysisValidationError(
            f"Une Cross Analyse requiert entre {MIN_CROSS_SOURCES} et {MAX_CROSS_SOURCES} analyses source."
        )
    if not all(isinstance(source, Mapping) for source in source_analyses):
        raise CrossAnalysisValidationError("Chaque analyse source doit être un objet valide.")
    source_ids = [_clean_text(source.get("source_id"), 80) for source in source_analyses]
    if not all(source_ids) or len(set(source_ids)) != len(source_ids):
        raise CrossAnalysisValidationError("Chaque analyse Cross doit porter un source_id unique.")

    categories = (
        "emotions", "fears", "aspirations", "frustrations", "beliefs",
        "motivations", "objections", "themes", "behavioral_signals",
    )
    comparisons = {category: _cross_signals(source_analyses, category) for category in categories}

    total_comments = sum(
        int((source.get("comment_stats") or {}).get("total_comments") or 0)
        for source in source_analyses
    )
    source_with_data = sum(
        1 for source in source_analyses
        if int((source.get("comment_stats") or {}).get("total_comments") or 0) > 0
    )
    source_confidences = []
    for source in source_analyses:
        raw = (source.get("comment_stats") or {}).get("confidence_score", 0)
        try:
            raw = float(raw)
        except (TypeError, ValueError):
            raw = 0.0
        source_confidences.append(raw / 100 if raw > 1 else raw)
    avg_source_confidence = sum(source_confidences) / max(len(source_confidences), 1)
    source_coverage = source_with_data / max(len(source_analyses), 1)
    sample_factor = min(total_comments / (len(source_analyses) * 50), 1.0)
    confidence_score = round(100 * (0.45 * source_coverage + 0.30 * sample_factor + 0.25 * avg_source_confidence), 1)

    all_convergences = []
    all_divergences = []
    all_specific = []
    evidence_index: Dict[str, Dict[str, Any]] = {}
    for category, payload in comparisons.items():
        for item in payload["convergences"]:
            insight_id = _signal_insight_id(category, item["label"])
            enriched = {**item, "category": category, "insight_id": insight_id}
            all_convergences.append(enriched)
            evidence_index[insight_id] = {
                "category": category,
                "label": item["label"],
                "source_signals": item["sources"],
                "representative_source_evidence": _representative_source_evidence(
                    source_analyses, item["sources"]
                ),
            }
        for item in payload["divergences"]:
            insight_id = _signal_insight_id(category, item["label"])
            enriched = {**item, "category": category, "insight_id": insight_id}
            all_divergences.append(enriched)
            evidence_index.setdefault(insight_id, {
                "category": category,
                "label": item["label"],
                "source_signals": item["sources"],
                "representative_source_evidence": _representative_source_evidence(
                    source_analyses, item["sources"]
                ),
            })
        for item in payload["source_specific"]:
            insight_id = _signal_insight_id(category, item["label"])
            enriched = {**item, "category": category, "insight_id": insight_id}
            all_specific.append(enriched)
            evidence_index.setdefault(insight_id, {
                "category": category,
                "label": item["label"],
                "source_signals": item["sources"],
                "representative_source_evidence": _representative_source_evidence(
                    source_analyses, item["sources"]
                ),
            })

    common_core = {}
    for category in ("emotions", "fears", "aspirations", "frustrations", "beliefs", "motivations"):
        items = comparisons[category]["convergences"]
        if items:
            common_core[f"dominant_{category.rstrip('s')}"] = {
                "label": items[0]["label"],
                "sources_count": items[0]["sources_count"],
                "interpretation_status": "pending_llm",
            }

    oppositions = _detect_stance_oppositions(source_analyses)
    quality = _cross_quality(source_analyses)
    return {
        "schema_version": CROSS_ANALYSIS_SCHEMA_VERSION,
        "analysis_mode": "cross",
        "cross_summary": {
            "status": "measured_pending_interpretation",
            "sources_count": len(source_analyses),
            "comments_count": total_comments,
            "message": "Les signaux ont été comparés par source. La conclusion psychologique sera formulée à partir de ces preuves.",
        },
        "common_psychological_core": {
            **common_core,
            "evidence_based_signals": all_convergences,
            "interpretation_status": "pending_llm",
        },
        "convergences": all_convergences,
        "divergences": all_divergences,
        "oppositions": oppositions,
        "source_specific_signals": all_specific,
        "shared_emotions": comparisons["emotions"]["convergences"],
        "shared_fears": comparisons["fears"]["convergences"],
        "shared_aspirations": comparisons["aspirations"]["convergences"],
        "shared_frustrations": comparisons["frustrations"]["convergences"],
        "shared_beliefs": comparisons["beliefs"]["convergences"],
        "shared_motivations": comparisons["motivations"]["convergences"],
        "shared_objections": comparisons["objections"]["convergences"],
        "shared_themes": comparisons["themes"]["convergences"],
        "cross_personas": [],
        "technical_summary": {
            "analysis_mode": "source_balanced_comparison",
            "source_count": len(source_analyses),
            "comments_count": total_comments,
            "data_quality": quality,
            "methods": [
                "analyses_individuelles_existantes",
                "convergence_par_couverture_source",
                "divergence_par_ecart_d_intensite",
            ],
        },
        "evidence_index": evidence_index,
        "confidence": {
            "score": confidence_score,
            "level": "high" if confidence_score >= 75 else "medium" if confidence_score >= 45 else "low",
            "method": "source_balanced_deterministic",
            "sources_count": len(source_analyses),
            "sources_with_data": source_with_data,
            "total_comments": total_comments,
        },
        "data_quality": quality,
        "source_ids": source_ids,
        "source_analyses": list(source_analyses),
    }
