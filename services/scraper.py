import os
import re
import json
import time
import httplib2
import requests
from dotenv import load_dotenv
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# Même délai que les appels RapidAPI de ce fichier (timeout=15 plus bas).
# Sans timeout explicite, httplib2 n'en applique aucun par défaut : une
# connexion qui reste ouverte peut bloquer le thread de requête indéfiniment —
# critique sur un déploiement à un seul worker (voir Procfile).
_YOUTUBE_API_TIMEOUT_SECONDS = 15

_env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
load_dotenv(_env_path, override=True)


class RapidAPIUnavailable(Exception):
    """La clé RapidAPI est valide mais non abonnée à l'API demandée (401/403)."""
    def __init__(self, platform):
        self.platform = platform
        super().__init__(f"RapidAPI non abonné pour {platform}")


class SocialCollectionError(RuntimeError):
    """Échec de collecte Instagram/TikTok avec une cause identifiée.

    Pendant des plateformes sociales de ``YouTubeCollectionError``. Avant
    cette classe, ces collecteurs renvoyaient ``([], {})`` pour **cinq
    situations distinctes** — clé absente, lien non reconnu, API en panne,
    exception réseau, et aucun commentaire réellement présent. L'appelant ne
    pouvait pas les distinguer : l'utilisateur recevait un écran vide, sans
    savoir si son lien était mauvais ou si le service était tombé.

    Un seul de ces cas reste un retour vide, et c'est le seul qui le mérite :
    la collecte a réussi et la publication n'a pas de commentaire.
    """
    def __init__(self, platform, reason, message):
        self.platform = platform
        self.reason = reason
        super().__init__(message)


# Causes distinguées, et ce qu'elles impliquent pour l'appelant.
SOCIAL_ERROR_MESSAGES = {
    'apiKeyMissing': ("La collecte {platform} n'est pas configurée côté Gabriel. "
                      "Collez vos commentaires directement, ou réessayez plus tard."),
    'invalidUrl':    ("Ce lien {platform} n'est pas reconnu. Collez l'adresse d'une "
                      "publication précise."),
    'apiError':      ("La collecte {platform} a échoué. Réessayez dans quelques "
                      "minutes, ou collez vos commentaires directement."),
}


def _social_error(platform, reason):
    modele = SOCIAL_ERROR_MESSAGES.get(reason, "Collecte {platform} impossible.")
    return SocialCollectionError(platform, reason,
                                 modele.format(platform=platform.capitalize()))


def _is_link(value):
    """Un lien collé, par opposition à des commentaires collés à la main.

    Cette distinction décide de tout : sur du texte libre, un collecteur qui
    lèverait une erreur casserait le collage manuel, qui fonctionne
    aujourd'hui même sans clé API.
    """
    return (value or '').strip().lower().startswith(('http://', 'https://', 'www.'))


class YouTubeCollectionError(RuntimeError):
    """Erreur de collecte YouTube avec une cause identifiée (``reason``),
    au lieu d'un message générique unique pour vidéo privée, supprimée,
    commentaires désactivés ou quota dépassé — des situations que
    l'utilisateur (et l'admin, pour le quota) doivent pouvoir distinguer."""
    def __init__(self, reason, message):
        self.reason = reason
        super().__init__(message)


# Erreurs transitoires : le prochain essai peut réussir, ça vaut la peine de
# réessayer. Le quota (dépassement journalier), les vidéos privées/supprimées
# et les commentaires désactivés sont permanents pour la requête en cours —
# réessayer ne changerait rien, mieux vaut échouer vite avec un message clair.
_YOUTUBE_RETRYABLE_REASONS = {'rateLimitExceeded', 'userRateLimitExceeded', 'backendError', 'internalError'}
_YOUTUBE_RETRYABLE_STATUSES = {500, 502, 503, 504}

_YOUTUBE_ERROR_MESSAGES = {
    'commentsDisabled': "Les commentaires sont désactivés sur cette vidéo.",
    'videoNotFound': "Cette vidéo est introuvable, privée ou a été supprimée.",
    'quotaExceeded': "Le quota YouTube quotidien est dépassé. Réessayez plus tard.",
    'dailyLimitExceeded': "Le quota YouTube quotidien est dépassé. Réessayez plus tard.",
    'forbidden': "Accès refusé à cette vidéo (privée ou restreinte).",
}


def _youtube_error_reason(http_error):
    """Lit le motif structuré de l'erreur (format standard des API Google),
    plutôt que de se rabattre uniquement sur le code HTTP générique."""
    try:
        body = json.loads(http_error.content.decode('utf-8'))
        errors = (body.get('error') or {}).get('errors') or []
        if errors:
            return errors[0].get('reason', '')
    except Exception:
        pass
    return ''


def _call_youtube_with_retry(fn, *, max_attempts=3):
    """Rejoue une erreur transitoire avec un backoff court ; échoue
    immédiatement — avec un message identifiant la cause — sur une erreur
    permanente qu'aucun nouvel essai ne résoudrait."""
    last_exc = None
    for attempt in range(max_attempts):
        try:
            return fn()
        except HttpError as exc:
            last_exc = exc
            reason = _youtube_error_reason(exc)
            status = getattr(exc.resp, 'status', None)
            retryable = reason in _YOUTUBE_RETRYABLE_REASONS or status in _YOUTUBE_RETRYABLE_STATUSES
            if retryable and attempt < max_attempts - 1:
                time.sleep(min(2 ** attempt, 8))
                continue
            message = _YOUTUBE_ERROR_MESSAGES.get(reason, f"Erreur YouTube ({reason or status or 'inconnue'}).")
            raise YouTubeCollectionError(reason or str(status or ''), message) from exc
    raise YouTubeCollectionError('unknown', "Erreur YouTube inconnue.") from last_exc


def extract_youtube_id(url_or_id):
    patterns = [
        r'(?:v=|youtu\.be/)([a-zA-Z0-9_-]{11})',
        r'shorts/([a-zA-Z0-9_-]{11})',
        r'(?:embed|live)/([a-zA-Z0-9_-]{11})',
        r'^([a-zA-Z0-9_-]{11})$'
    ]
    for pattern in patterns:
        match = re.search(pattern, url_or_id)
        if match:
            return match.group(1)
    return None  # aucun ID de vidéo valide (chaîne, playlist, handle…)


def scrape_youtube(url_or_id, max_comments=150):
    """Collecte les commentaires principaux d'une vidéo YouTube.

    ``max_comments`` est additif : l'analyse simple conserve son comportement
    historique à 150 commentaires tant qu'elle ne transmet pas d'option.
    La limite physique est bornée à 200 pour préserver le quota et la latence
    déjà calibrés du collecteur actuel.
    """
    api_key = os.environ.get("YOUTUBE_API_KEY")
    if not api_key:
        # Erreur de configuration serveur (pas une faute utilisateur) → 500 + log
        raise RuntimeError("YOUTUBE_API_KEY manquante — configurez-la dans les variables d'environnement Render.")

    video_id = extract_youtube_id(url_or_id)
    if not video_id:
        # URL de chaîne (@handle, /channel/, /c/, /user/), playlist ou lien invalide
        raise ValueError(
            "Ce lien n'est pas une vidéo. Collez l'URL d'une vidéo YouTube précise "
            "(ex. youtube.com/watch?v=…), pas d'une chaîne ou d'une playlist."
        )
    youtube = build(
        'youtube', 'v3', developerKey=api_key,
        http=httplib2.Http(timeout=_YOUTUBE_API_TIMEOUT_SECONDS),
    )

    try:
        max_comments = int(max_comments)
    except (TypeError, ValueError):
        max_comments = 150
    max_comments = max(1, min(max_comments, 200))

    # Récupère aussi le titre de la vidéo pour contexte. L'identité de la
    # vidéo est disponible même si l'appel de métadonnées échoue.
    video_info = {
        'video_id': video_id,
        'canonical_url': f'https://www.youtube.com/watch?v={video_id}',
    }
    try:
        # 'statistics' et 'contentDetails' ajoutés : vues/likes/nb commentaires
        # et durée n'étaient jamais capturés (seul 'snippet' était demandé),
        # alors que le contrat SourceAnalysis les prévoit explicitement.
        vr = youtube.videos().list(part='snippet,statistics,contentDetails', id=video_id).execute()
        if vr.get('items'):
            item = vr['items'][0]
            snip = item.get('snippet', {})
            stats = item.get('statistics', {})
            details = item.get('contentDetails', {})
            video_info.update({
                'title': snip.get('title', ''),
                'channel': snip.get('channelTitle', ''),
                'description': snip.get('description', '')[:600],
                'published_at': snip.get('publishedAt', ''),
                # likeCount est absent si le créateur masque le compteur — ne
                # jamais le confondre avec "0 like réel".
                'view_count': int(stats.get('viewCount', 0) or 0),
                'like_count': int(stats['likeCount']) if 'likeCount' in stats else None,
                'comment_count': int(stats.get('commentCount', 0) or 0),
                # Format ISO 8601 natif de l'API (ex: "PT4M13S") — pas reformaté
                # ici pour rester une donnée brute, pas une interprétation.
                'duration': details.get('duration', ''),
            })
    except Exception:
        pass

    def _fetch_comments(order, target=200):
        result = []
        page_token = None
        while len(result) < target:
            batch = min(target - len(result), 100)
            resp = _call_youtube_with_retry(lambda: youtube.commentThreads().list(
                part='snippet',
                videoId=video_id,
                maxResults=batch,
                pageToken=page_token,
                textFormat='plainText',
                order=order
            ).execute())
            for item in resp.get('items', []):
                top_level = item['snippet']['topLevelComment']
                top = top_level['snippet']
                text = top.get('textDisplay', '').strip()
                if text:
                    result.append({
                        # Champs historiques, consommés par l'analyse simple.
                        'text':   text,
                        'likes':  top.get('likeCount', 0),
                        'author': top.get('authorDisplayName', ''),
                        # Champs additifs : requis par la provenance Cross Analyse.
                        'comment_id': top_level.get('id', ''),
                        'external_comment_id': top_level.get('id', ''),
                        'video_id': video_id,
                        'published_at': top.get('publishedAt', ''),
                        'updated_at': top.get('updatedAt', ''),
                        'reply_count': item.get('snippet', {}).get('totalReplyCount', 0),
                    })
            page_token = resp.get('nextPageToken')
            if not page_token or len(result) >= target:
                break
        return result

    # Priorité : pertinence (meilleur signal), fallback temps si peu de résultats
    comments = _fetch_comments('relevance', target=max_comments)
    if len(comments) < 20:
        by_time = _fetch_comments('time', target=max_comments)
        if len(by_time) > len(comments):
            comments = by_time

    # Trier par likes décroissants → les signaux les plus amplifiés d'abord
    comments.sort(key=lambda c: c.get('likes', 0), reverse=True)

    # Garder les commentaires les plus représentatifs sans dépasser la limite
    # explicitement demandée par l'appelant.
    return comments[:max_comments], video_info


def scrape_instagram_rapidapi(url):
    """Collecte les commentaires d'une publication Instagram.

    Sur un lien, tout échec lève une ``SocialCollectionError`` portant sa
    cause. Sur du texte libre, la fonction rend un résultat vide sans lever :
    l'appelant se rabat alors sur le collage manuel, qui doit continuer à
    fonctionner même sans clé API.
    """
    lien = _is_link(url)
    api_key = os.environ.get("RAPIDAPI_KEY")
    if not api_key:
        if lien:
            raise _social_error('instagram', 'apiKeyMissing')
        return [], {}

    # Supporte /p/ et /reel/
    match = re.search(r'/(?:p|reel)/([A-Za-z0-9_-]+)', url)
    if not match:
        if lien:
            raise _social_error('instagram', 'invalidUrl')
        return [], {}
    shortcode = match.group(1)

    headers = {
        "X-RapidAPI-Key": api_key,
        "X-RapidAPI-Host": "instagram-scraper-api2.p.rapidapi.com"
    }

    try:
        response = requests.get(
            "https://instagram-scraper-api2.p.rapidapi.com/v1/comments",
            headers=headers,
            params={"code_or_id_or_url": shortcode},
            timeout=15
        )
        if response.status_code in (401, 403):
            print(f"[SCRAPER] RapidAPI Instagram {response.status_code} — clé non abonnée à instagram-scraper-api2.")
            raise RapidAPIUnavailable('instagram')
        if response.status_code != 200:
            print(f"[SCRAPER] Instagram HTTP {response.status_code}")
            raise _social_error('instagram', 'apiError')

        data = response.json()
        comments = []
        for item in data.get('data', {}).get('items', []):
            text = item.get('text', '').strip()
            if text:
                comments.append({
                    'text': text,
                    'likes': item.get('comment_like_count', 0),
                    'author': item.get('user', {}).get('username', '')
                })
        # Zéro commentaire ici est un vrai résultat : la collecte a réussi et
        # la publication n'en a pas. C'est le seul cas qui mérite un vide.
        return comments, {}
    except (RapidAPIUnavailable, SocialCollectionError):
        raise
    except Exception as error:
        print(f"[SCRAPER] Instagram échec réseau : {error}")
        raise _social_error('instagram', 'apiError') from error


def scrape_tiktok_rapidapi(url):
    """Récupère les commentaires TikTok via RapidAPI (tiktok-api23).

    Même contrat qu'Instagram : sur un lien, tout échec lève une
    ``SocialCollectionError`` portant sa cause ; sur du texte libre, retour
    vide pour laisser le collage manuel fonctionner.
    """
    lien = _is_link(url)
    if not lien:
        # Du texte libre n'a rien à collecter : l'appelant se rabattra sur le
        # collage manuel. Avant, cette entrée déclenchait quand même un appel
        # réseau — dépense inutile, et une clé non abonnée y faisait échouer
        # un collage manuel parfaitement valide.
        return [], {}

    api_key = os.environ.get("RAPIDAPI_KEY")
    if not api_key:
        raise _social_error('tiktok', 'apiKeyMissing')

    # Résoudre les URLs courtes vm.tiktok.com → URL canonique
    canonical = url
    if 'vm.tiktok.com' in url or 'vt.tiktok.com' in url:
        try:
            r = requests.head(url, allow_redirects=True, timeout=8)
            canonical = r.url
        except Exception:
            pass

    headers = {
        "X-RapidAPI-Key":  api_key,
        "X-RapidAPI-Host": "tiktok-api23.p.rapidapi.com"
    }

    video_info = {}
    comments   = []
    aweme      = ''   # initialisé ici — jamais UnboundLocalError

    # 1. Infos vidéo (titre + auteur) pour le contexte d'analyse
    try:
        meta = requests.get(
            "https://tiktok-api23.p.rapidapi.com/api/post/detail",
            headers=headers,
            params={"url": canonical},
            timeout=15
        )
        if meta.status_code in (401, 403):
            print(f"[SCRAPER] RapidAPI TikTok {meta.status_code} — clé non abonnée à tiktok-api23.")
            raise RapidAPIUnavailable('tiktok')
        if meta.status_code == 200:
            item   = meta.json().get('data', {}).get('itemInfo', {}).get('itemStruct', {})
            desc   = item.get('desc', '')
            author = item.get('author', {}).get('uniqueId', '')
            aweme  = item.get('id', '')
            if desc or author:
                video_info = {'title': desc, 'channel': f"@{author}"}
    except RapidAPIUnavailable:
        raise
    except Exception:
        pass

    # Extraire l'aweme_id depuis l'URL si l'appel méta a échoué
    if not aweme:
        m = re.search(r'/video/(\d+)', canonical)
        aweme = m.group(1) if m else ''

    if not aweme:
        # Ni l'appel méta ni l'URL ne donnent l'identifiant de la vidéo :
        # le lien n'est pas exploitable, et le dire vaut mieux qu'un vide.
        if lien:
            raise _social_error('tiktok', 'invalidUrl')
        return [], video_info

    # 2. Commentaires (jusqu'à 100)
    cursor = 0
    premier_appel = True
    while len(comments) < 100:
        try:
            resp = requests.get(
                "https://tiktok-api23.p.rapidapi.com/api/comment/list",
                headers=headers,
                params={"aweme_id": aweme, "count": 50, "cursor": cursor},
                timeout=15
            )
            if resp.status_code != 200:
                # Échouer au tout premier appel n'est pas la même chose que
                # s'arrêter en cours de pagination : le premier ne rend rien
                # du tout, le second garde ce qui a déjà été collecté.
                if premier_appel and lien:
                    print(f"[SCRAPER] TikTok HTTP {resp.status_code}")
                    raise _social_error('tiktok', 'apiError')
                break
            data = resp.json()
            items = data.get('data', {}).get('comments', [])
            if not items:
                break
            for c in items:
                text = c.get('text', '').strip()
                if text:
                    comments.append({
                        'text':   text,
                        'likes':  c.get('digg_count', 0),
                        'author': c.get('user', {}).get('unique_id', '')
                    })
            if not data.get('data', {}).get('has_more'):
                break
            cursor = data.get('data', {}).get('cursor', cursor + 50)
            premier_appel = False
        except SocialCollectionError:
            raise
        except Exception as error:
            if premier_appel and lien:
                print(f"[SCRAPER] TikTok échec réseau : {error}")
                raise _social_error('tiktok', 'apiError') from error
            break

    # Trier par likes décroissants, garder les 100 plus représentatifs
    comments.sort(key=lambda c: c.get('likes', 0), reverse=True)
    return comments[:100], video_info


def parse_manual_comments(text):
    if not text or not text.strip():
        return []
    lines = [line.strip() for line in text.split('\n') if line.strip() and len(line.strip()) > 2]
    return [{'text': line, 'likes': 0, 'author': 'inconnu'} for line in lines]
