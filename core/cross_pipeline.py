"""Orchestration backend de la Cross Analyse, sans dépendance Flask.

Le pipeline ne connaît ni la base ni les crédits. Il collecte chaque source,
réutilise un callback d'analyse individuelle fourni par l'application, puis
construit la comparaison déterministe. Cela protège le pipeline simple de tout
changement de comportement.
"""

from __future__ import annotations

import copy
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable, Dict, List, Mapping, Sequence

from core.cross_analysis import (
    CrossAnalysisValidationError,
    attach_source_metadata,
    build_cross_analysis,
    build_source_analysis,
    clean_and_deduplicate_source_comments,
)
from services.youtube_provider import YouTubeProvider


class CrossPipelineError(RuntimeError):
    """Erreur de pipeline ne permettant pas une comparaison fiable."""


class CrossAnalysisPipeline:
    """Collecte et analyse N sources avec une concurrence bornée."""

    def __init__(self, youtube_provider: YouTubeProvider | None = None, cache_ttl_seconds: int = 3600):
        self.youtube_provider = youtube_provider or YouTubeProvider()
        self.cache_ttl_seconds = max(int(cache_ttl_seconds), 60)
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._analysis_cache: Dict[str, Dict[str, Any]] = {}
        self._cache_lock = threading.Lock()

    @staticmethod
    def _cache_key(source: Mapping[str, Any]) -> str:
        return f"{source.get('platform', '')}:{source.get('external_id', '')}"

    @classmethod
    def _analysis_cache_key(cls, source: Mapping[str, Any], options: Mapping[str, Any]) -> str:
        # Un résultat LLM est potentiellement sensible au contexte d'un
        # utilisateur. Il ne peut donc jamais être partagé entre comptes,
        # même si la vidéo YouTube est identique.
        scope = str(options.get('_cache_scope') or '')
        return f"{scope}:{cls._cache_key(source)}"

    def _read_cache(self, source: Mapping[str, Any]) -> Dict[str, Any] | None:
        key = self._cache_key(source)
        with self._cache_lock:
            entry = self._cache.get(key)
            if not entry or time.monotonic() - entry["created_at"] > self.cache_ttl_seconds:
                self._cache.pop(key, None)
                return None
            return copy.deepcopy(entry["payload"])

    def _write_cache(self, source: Mapping[str, Any], payload: Mapping[str, Any]) -> None:
        with self._cache_lock:
            self._cache[self._cache_key(source)] = {
                "created_at": time.monotonic(),
                "payload": copy.deepcopy(dict(payload)),
            }

    def _read_analysis_cache(self, source: Mapping[str, Any], options: Mapping[str, Any]) -> Dict[str, Any] | None:
        if not options.get('_cache_scope'):
            return None
        key = self._analysis_cache_key(source, options)
        with self._cache_lock:
            entry = self._analysis_cache.get(key)
            if not entry or time.monotonic() - entry['created_at'] > self.cache_ttl_seconds:
                self._analysis_cache.pop(key, None)
                return None
            return copy.deepcopy(entry['result'])

    def _write_analysis_cache(self, source: Mapping[str, Any], options: Mapping[str, Any], result: Mapping[str, Any]) -> None:
        if not options.get('_cache_scope'):
            return
        key = self._analysis_cache_key(source, options)
        with self._cache_lock:
            self._analysis_cache[key] = {
                'created_at': time.monotonic(),
                'result': copy.deepcopy(dict(result)),
            }

    def collect_source(self, source: Mapping[str, Any], options: Mapping[str, Any]) -> Dict[str, Any]:
        """Collecte une source et applique la préparation data déterministe."""
        cached = None if options.get("refresh") else self._read_cache(source)
        if cached:
            payload = cached
            payload["cache_hit"] = True
        else:
            if source.get("platform") != "youtube":
                raise CrossPipelineError("Plateforme Cross non prise en charge.")
            comments, video_metadata = self.youtube_provider.collect(
                source,
                max_comments=options["max_comments_per_source"],
                include_replies=options["include_replies"],
            )
            payload = {
                "comments": comments,
                "video_metadata": video_metadata,
                "cache_hit": False,
            }
            self._write_cache(source, payload)

        resolved_source = attach_source_metadata(source, payload.get("video_metadata") or {})
        prepared = clean_and_deduplicate_source_comments(payload.get("comments") or [], resolved_source)
        if not prepared["retained_comments"]:
            raise CrossPipelineError("Aucun commentaire exploitable n'a été collecté pour cette source.")

        return {
            "source": resolved_source,
            "raw_comments": prepared["raw_comments"],
            "retained_comments": prepared["retained_comments"],
            "dataset": prepared["dataset"],
            "cache_hit": bool(payload.get("cache_hit")),
        }

    def run(
        self,
        sources: Sequence[Mapping[str, Any]],
        options: Mapping[str, Any],
        analyze_source: Callable[[Mapping[str, Any], List[Dict[str, Any]], Dict[str, Any] | None], Mapping[str, Any]],
        *,
        progress_cb: Callable[[str, int], None] | None = None,
        source_status_cb: Callable[[Mapping[str, Any], str, Mapping[str, Any] | None], None] | None = None,
    ) -> Dict[str, Any]:
        """Exécute collecte → simples analyses → comparaison, source par source.

        ``analyze_source`` est la seule dépendance du Psychologue existant :
        l'application lui transmet ``gabriel.run_psycho`` emballé avec sa
        persistance habituelle. Ainsi, aucune logique Cross n'entre dans
        ``core.analyzer``.

        ``analyze_source(source, comments, cached_result)`` est **toujours**
        appelée, même quand un résultat récent existe déjà : ce pipeline ne
        connaît ni la base ni les crédits (voir le docstring du module), donc
        il ne peut pas décider seul de réutiliser une analyse. Il transmet
        simplement ce qu'il a vu passer ; c'est à l'appelant (l'application)
        de choisir de rejouer ``gabriel.run_psycho`` ou non, et dans tous les
        cas d'attribuer une identité et une persistance propres à *cette*
        Cross Analyse. Sans ça, une Cross ultérieure hériterait silencieusement
        de l'``analysis_id`` d'une session précédente.
        """
        def progress(step: str, pct: int) -> None:
            if progress_cb:
                progress_cb(step, max(0, min(int(pct), 100)))

        def source_status(source: Mapping[str, Any], status: str, payload: Mapping[str, Any] | None = None) -> None:
            if source_status_cb:
                source_status_cb(source, status, payload)

        source_count = len(sources)
        collected: List[Dict[str, Any]] = []
        failed_sources: List[Dict[str, Any]] = []
        progress("collecte_sources", 3)

        # La collecte est séquentielle afin de respecter le quota YouTube et
        # de rendre les erreurs par vidéo immédiatement lisibles.
        for index, source in enumerate(sources):
            source_status(source, "collecting")
            try:
                collected_source = self.collect_source(source, options)
                collected.append(collected_source)
                source_status(collected_source["source"], "collected", {
                    "dataset": collected_source["dataset"],
                    "cache_hit": collected_source["cache_hit"],
                    # Preuve primaire conservée côté backend. Les doublons
                    # exacts ne sont pas analysés deux fois, mais ils restent
                    # traçables et rattachés à leur source d'origine.
                    "raw_comments": collected_source["raw_comments"],
                })
            except Exception as exc:
                failed_sources.append({
                    "source_id": source.get("source_id", ""),
                    "position": source.get("position"),
                    "stage": "collection",
                    "error": str(exc)[:300],
                })
                source_status(source, "failed", failed_sources[-1])
            progress("collecte_sources", 5 + round(20 * (index + 1) / max(source_count, 1)))

        if len(collected) < 2:
            raise CrossPipelineError(
                "Au moins deux sources exploitables sont nécessaires pour produire une Cross Analyse."
            )

        source_analyses: List[Dict[str, Any]] = []
        progress("analyses_individuelles", 27)
        # Une analyse individuelle comporte déjà plusieurs appels LLM en
        # parallèle. Par défaut, une seule source est exécutée à la fois ;
        # l'option est bornée à deux pour ne pas saturer Render ou Mistral.
        workers = min(int(options.get("max_parallel_sources", 1)), len(collected), 2)
        with ThreadPoolExecutor(max_workers=max(workers, 1)) as executor:
            futures: Dict[Any, Dict[str, Any]] = {}
            cache_offered = set()
            for collected_source in collected:
                source = collected_source["source"]
                source_status(source, "analyzing")
                cached_result = None if options.get('refresh') else self._read_analysis_cache(source, options)
                if cached_result is not None:
                    source_status(source, "reusing")
                    cache_offered.add(source.get('source_id', ''))
                # L'appelant décide toujours de l'identité et de la persistance,
                # qu'un résultat récent soit disponible ou non.
                future = executor.submit(
                    analyze_source, source, collected_source["retained_comments"], cached_result
                )
                futures[future] = collected_source

            completed_count = 0
            for future in as_completed(futures):
                collected_source = futures[future]
                source = collected_source["source"]
                try:
                    result = future.result()
                    self._write_analysis_cache(source, options, result)
                    source_analysis = build_source_analysis(
                        source,
                        result,
                        collected_source["retained_comments"],
                        dataset=collected_source["dataset"],
                    )
                    # ``analyze_source`` est seul à savoir s'il a réellement
                    # réutilisé le résultat proposé ; à défaut, on retombe sur
                    # le simple fait qu'un résultat récent existait.
                    if 'reused_from_cache' in result:
                        source_analysis['analysis_cache_hit'] = bool(result.get('reused_from_cache'))
                    else:
                        source_analysis['analysis_cache_hit'] = source.get('source_id', '') in cache_offered
                    source_analyses.append(source_analysis)
                    source_status(source, "completed", source_analysis)
                except Exception as exc:
                    failed_sources.append({
                        "source_id": source.get("source_id", ""),
                        "position": source.get("position"),
                        "stage": "individual_analysis",
                        "error": str(exc)[:300],
                    })
                    source_status(source, "failed", failed_sources[-1])
                completed_count += 1
                progress("analyses_individuelles", 27 + round(53 * completed_count / max(len(collected), 1)))

        if len(source_analyses) < 2:
            raise CrossPipelineError(
                "La Cross Analyse ne peut pas comparer moins de deux analyses individuelles réussies."
            )

        source_analyses.sort(key=lambda item: next(
            (source.get("position", 0) for source in sources if source.get("source_id") == item.get("source_id")), 0
        ))
        progress("comparaison", 83)
        cross_result = build_cross_analysis(source_analyses)
        cross_result["status"] = "partial_success" if failed_sources else "completed"
        cross_result["failed_sources"] = failed_sources
        cross_result["sources"] = [
            {
                "source_id": item.get("source_id"),
                "platform": item.get("platform"),
                "metadata": item.get("metadata", {}),
                "analysis_id": item.get("analysis_id", ""),
                "data_quality": item.get("data_quality", {}),
            }
            for item in source_analyses
        ]
        progress("comparaison", 90)
        return cross_result
