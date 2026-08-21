"""Adaptateur YouTube pour les flux multi-source du Psychologue.

Le collecteur historique reste dans ``services.scraper``. Cette façade évite
de disperser la connaissance des URLs et des limites Cross dans les routes,
sans réécrire la collecte déjà utilisée par l'analyse simple.
"""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Tuple

from services.scraper import extract_youtube_id, scrape_youtube


class YouTubeProvider:
    """Provider V1 : métadonnées + commentaires principaux via l'API officielle."""

    platform = "youtube"

    def resolve_video(self, url: str) -> str:
        video_id = extract_youtube_id(url or "")
        if not video_id:
            raise ValueError("URL de vidéo YouTube invalide.")
        return video_id

    def collect(
        self,
        source: Mapping[str, Any],
        *,
        max_comments: int,
        include_replies: bool = False,
    ) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """Collecte une source sans faire croire que les réponses sont prises en charge.

        Les réponses nécessitent une pagination dédiée ``comments.list``. La
        V1 refuse l'option plutôt que de l'ignorer silencieusement.
        """
        if include_replies:
            raise NotImplementedError(
                "La collecte des réponses YouTube n'est pas encore disponible dans la Cross Analyse."
            )
        url = str(source.get("canonical_url") or source.get("input_url") or "")
        comments, metadata = scrape_youtube(url, max_comments=max_comments)
        return comments, metadata
