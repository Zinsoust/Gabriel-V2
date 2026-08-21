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




def _fetch_instagram_comments(url):
    from services.scraper import scrape_instagram_rapidapi
    comments, info = scrape_instagram_rapidapi(url)
    return {"comments": comments, "post_info": info}


def _fetch_tiktok_comments(url):
    from services.scraper import scrape_tiktok_rapidapi
    comments, info = scrape_tiktok_rapidapi(url)
    return {"comments": comments, "video_info": info}


FETCH_INSTAGRAM_COMMENTS = ToolSpec(
    id='collection.fetch_instagram_comments',
    name='Collecte des commentaires Instagram',
    description=(
        "Récupère les commentaires d'une publication Instagram (post ou reel). "
        "Sur un lien, tout échec porte sa cause : lien non reconnu, service "
        "indisponible, collecte non configurée."),
    category='collection',
    inputs=(ToolInput('url', "URL de la publication Instagram"),),
    output="{comments: [...], post_info: {}}",
    deterministic=False,   # les commentaires évoluent entre deux appels
    parallel_safe=True,
    cacheable=False,
    timeout_s=15,          # timeout HTTP de services/scraper.py
    cost_hint='Quota RapidAPI (instagram-scraper-api2) : 1 requête par publication.',
)

FETCH_TIKTOK_COMMENTS = ToolSpec(
    id='collection.fetch_tiktok_comments',
    name='Collecte des commentaires TikTok',
    description=(
        "Récupère les commentaires et les métadonnées d'une vidéo TikTok, "
        "jusqu'à 100, triés par likes. Résout les liens courts vm.tiktok.com."),
    category='collection',
    inputs=(ToolInput('url', "URL de la vidéo TikTok, courte ou canonique"),),
    output="{comments: [...], video_info: {title, channel}}",
    deterministic=False,
    parallel_safe=True,
    cacheable=False,
    timeout_s=15,
    # Deux appels au minimum — métadonnées puis commentaires — plus la
    # pagination : le coût n'est pas d'une requête par vidéo.
    cost_hint='Quota RapidAPI (tiktok-api23) : 2 requêtes minimum, plus une par page de 50 commentaires.',
)


def register_all() -> None:
    registry.register(FunctionTool(FETCH_YOUTUBE_COMMENTS, _fetch_youtube_comments))
    registry.register(FunctionTool(FETCH_INSTAGRAM_COMMENTS, _fetch_instagram_comments))
    registry.register(FunctionTool(FETCH_TIKTOK_COMMENTS, _fetch_tiktok_comments))


register_all()
