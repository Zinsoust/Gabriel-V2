import os
import re
import requests
from dotenv import load_dotenv
from googleapiclient.discovery import build

_env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
load_dotenv(_env_path, override=True)


def extract_youtube_id(url_or_id):
    patterns = [
        r'(?:v=|youtu\.be/)([a-zA-Z0-9_-]{11})',
        r'shorts/([a-zA-Z0-9_-]{11})',
        r'^([a-zA-Z0-9_-]{11})$'
    ]
    for pattern in patterns:
        match = re.search(pattern, url_or_id)
        if match:
            return match.group(1)
    return url_or_id.strip()


def scrape_youtube(url_or_id):
    api_key = os.environ.get("YOUTUBE_API_KEY")
    if not api_key:
        raise ValueError("YOUTUBE_API_KEY manquante dans .env")

    video_id = extract_youtube_id(url_or_id)
    youtube = build('youtube', 'v3', developerKey=api_key)

    # Récupère aussi le titre de la vidéo pour contexte
    video_info = {}
    try:
        vr = youtube.videos().list(part='snippet', id=video_id).execute()
        if vr.get('items'):
            snip = vr['items'][0]['snippet']
            video_info = {'title': snip.get('title', ''), 'channel': snip.get('channelTitle', '')}
    except Exception:
        pass

    comments = []
    next_page_token = None

    # Récupère 200 commentaires par pertinence YouTube
    while len(comments) < 200:
        batch = min(200 - len(comments), 100)
        response = youtube.commentThreads().list(
            part='snippet',
            videoId=video_id,
            maxResults=batch,
            pageToken=next_page_token,
            textFormat='plainText',
            order='relevance'
        ).execute()

        for item in response.get('items', []):
            top = item['snippet']['topLevelComment']['snippet']
            text = top.get('textDisplay', '').strip()
            if text:
                comments.append({
                    'text': text,
                    'likes': top.get('likeCount', 0),
                    'author': top.get('authorDisplayName', '')
                })

        next_page_token = response.get('nextPageToken')
        if not next_page_token or len(comments) >= 200:
            break

    # Trier par likes décroissants → les signaux les plus amplifiés d'abord
    comments.sort(key=lambda c: c.get('likes', 0), reverse=True)

    # Garder les 100 plus likés = échantillon représentatif de haute valeur
    return comments[:100], video_info


def scrape_instagram_rapidapi(url):
    api_key = os.environ.get("RAPIDAPI_KEY")
    if not api_key:
        return [], {}

    # Supporte /p/ et /reel/
    match = re.search(r'/(?:p|reel)/([A-Za-z0-9_-]+)', url)
    if not match:
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
        if response.status_code != 200:
            return [], {}

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
        return comments, {}
    except Exception:
        return [], {}


def scrape_tiktok_rapidapi(url):
    """Récupère les commentaires TikTok via RapidAPI (tiktok-api23)."""
    api_key = os.environ.get("RAPIDAPI_KEY")
    if not api_key:
        return [], {}

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
        if meta.status_code == 200:
            item   = meta.json().get('data', {}).get('itemInfo', {}).get('itemStruct', {})
            desc   = item.get('desc', '')
            author = item.get('author', {}).get('uniqueId', '')
            aweme  = item.get('id', '')
            if desc or author:
                video_info = {'title': desc, 'channel': f"@{author}"}
    except Exception:
        pass

    # Extraire l'aweme_id depuis l'URL si l'appel méta a échoué
    if not aweme:
        m = re.search(r'/video/(\d+)', canonical)
        aweme = m.group(1) if m else ''

    if not aweme:
        return [], video_info

    # 2. Commentaires (jusqu'à 100)
    cursor = 0
    while len(comments) < 100:
        try:
            resp = requests.get(
                "https://tiktok-api23.p.rapidapi.com/api/comment/list",
                headers=headers,
                params={"aweme_id": aweme, "count": 50, "cursor": cursor},
                timeout=15
            )
            if resp.status_code != 200:
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
        except Exception:
            break

    # Trier par likes décroissants, garder les 100 plus représentatifs
    comments.sort(key=lambda c: c.get('likes', 0), reverse=True)
    return comments[:100], video_info


def scrape_tiktok_meta(url):
    """Legacy — conservé pour compatibilité."""
    try:
        r = requests.get("https://www.tiktok.com/oembed", params={"url": url}, timeout=8)
        if r.status_code == 200:
            return r.json()
    except Exception:
        pass
    return {}


def parse_manual_comments(text):
    if not text or not text.strip():
        return []
    lines = [line.strip() for line in text.split('\n') if line.strip() and len(line.strip()) > 2]
    return [{'text': line, 'likes': 0, 'author': 'inconnu'} for line in lines]
