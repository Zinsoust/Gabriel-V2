"""Outils de collecte — le monde extérieur.

Premier outil hors calcul pur : il touche le réseau, dépend d'un quota
externe, et peut échouer de façons que Gabriel doit distinguer (vidéo privée,
commentaires désactivés, quota dépassé — chacune appelle une réaction
différente). Le contrat réseau (timeout, retry, taxonomie d'erreurs) vit déjà
dans ``services/scraper.py`` et n'est pas réécrit ici ; ce module le déclare.
"""

from tools.base import FunctionTool, ToolInput, ToolSpec
from tools.registry import registry


def _fetch_youtube_comments(url_or_id, max_comments=150):
    from services.scraper import scrape_youtube
    comments, video_info = scrape_youtube(url_or_id, max_comments=max_comments)
    return {"comments": comments, "video_info": video_info}


FETCH_YOUTUBE_COMMENTS = ToolSpec(
    id='collection.fetch_youtube_comments',
    name='Collecte des commentaires YouTube',
    description=(
        "Récupère les commentaires principaux et les métadonnées d'une "
        "vidéo YouTube via l'API officielle."),
    category='collection',
    inputs=(
        ToolInput('url_or_id', "URL ou identifiant de la vidéo YouTube"),
        ToolInput('max_comments', "Nombre maximum de commentaires (1-200, défaut 150)",
                  required=False),
    ),
    output=(
        "{comments: [...], video_info: {video_id, canonical_url, title, "
        "channel, view_count, like_count, comment_count, duration, ...}}"),
    deterministic=False,   # les commentaires évoluent entre deux appels
    parallel_safe=True,    # chaque appel ouvre son propre client API
    cacheable=False,       # des données vivantes ne doivent pas être servies périmées
    timeout_s=15,          # _YOUTUBE_API_TIMEOUT_SECONDS dans services/scraper.py
    cost_hint='Quota YouTube Data API v3 : ~1 unité + pagination des commentaires (jusqu\'à 100/page).',
)


def register_all() -> None:
    registry.register(FunctionTool(FETCH_YOUTUBE_COMMENTS, _fetch_youtube_comments))


register_all()
