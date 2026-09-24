"""services/scraper.py — le client YouTube Data API doit avoir un timeout.

Sans timeout explicite, httplib2 (le transport utilisé par le client Google
officiel) n'en applique aucun par défaut : une connexion qui reste ouverte
peut bloquer le thread de requête indéfiniment. Critique ici car l'app tourne
avec un seul worker (voir Procfile) — un appel YouTube qui pend bloquerait
tout le serveur, pas seulement l'utilisateur qui a lancé l'analyse.
"""

import os
import sys
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import httplib2
from googleapiclient.errors import HttpError

import services.scraper as scraper


def _http_error(status, reason):
    """Reproduit le format d'erreur standard des API Google (celui que
    YouTube Data API renvoie réellement pour commentsDisabled, videoNotFound,
    quotaExceeded, etc.)."""
    body = json.dumps({'error': {'errors': [{'reason': reason, 'message': reason}]}}).encode('utf-8')
    return HttpError(httplib2.Response({'status': status}), body)


class _FakeExecutable:
    def __init__(self, payload):
        self._payload = payload

    def execute(self):
        return self._payload


class _FakeYouTubeClient:
    def videos(self):
        return self

    def commentThreads(self):
        return self

    def list(self, **kwargs):
        if 'videoId' in kwargs:
            return _FakeExecutable({'items': []})
        return _FakeExecutable({'items': [{
            'snippet': {
                'title': 'Titre test', 'channelTitle': 'Chaîne test',
                'description': '', 'publishedAt': '2026-01-01T00:00:00Z',
            },
            'statistics': {'viewCount': '12345', 'likeCount': '678', 'commentCount': '90'},
            'contentDetails': {'duration': 'PT4M13S'},
        }]})


def test_scrape_youtube_configures_a_client_side_timeout(monkeypatch):
    monkeypatch.setenv('YOUTUBE_API_KEY', 'test-key')
    captured = {}

    def fake_build(service, version, **kwargs):
        captured.update(kwargs)
        return _FakeYouTubeClient()

    monkeypatch.setattr(scraper, 'build', fake_build)

    scraper.scrape_youtube('https://www.youtube.com/watch?v=dQw4w9WgXcQ', max_comments=10)

    assert 'http' in captured, "aucun transport http= passé à build() — timeout non configurable"
    assert isinstance(captured['http'], httplib2.Http)
    assert captured['http'].timeout == 15


def test_scrape_youtube_still_returns_comments_and_metadata(monkeypatch):
    """Non-régression : le comportement fonctionnel ne doit pas changer."""
    monkeypatch.setenv('YOUTUBE_API_KEY', 'test-key')
    monkeypatch.setattr(scraper, 'build', lambda *a, **k: _FakeYouTubeClient())

    comments, metadata = scraper.scrape_youtube(
        'https://www.youtube.com/watch?v=dQw4w9WgXcQ', max_comments=10
    )

    assert comments == []
    assert metadata['title'] == 'Titre test'
    assert metadata['video_id'] == 'dQw4w9WgXcQ'
    # Vues/likes/nb commentaires/durée : jamais capturés avant ce correctif
    # (seule la partie 'snippet' était demandée à l'API).
    assert metadata['view_count'] == 12345
    assert metadata['like_count'] == 678
    assert metadata['comment_count'] == 90
    assert metadata['duration'] == 'PT4M13S'


def test_scrape_youtube_leaves_like_count_none_when_the_creator_hides_it(monkeypatch):
    """likeCount est absent de la réponse API quand le créateur masque le
    compteur — ça ne doit jamais être confondu avec 0 like réel."""
    monkeypatch.setenv('YOUTUBE_API_KEY', 'test-key')

    class _HiddenLikesClient(_FakeYouTubeClient):
        def list(self, **kwargs):
            if 'videoId' in kwargs:
                return _FakeExecutable({'items': []})
            return _FakeExecutable({'items': [{
                'snippet': {'title': 'x', 'channelTitle': 'x', 'description': '', 'publishedAt': ''},
                'statistics': {'viewCount': '100', 'commentCount': '5'},  # pas de likeCount
                'contentDetails': {'duration': 'PT1M'},
            }]})

    monkeypatch.setattr(scraper, 'build', lambda *a, **k: _HiddenLikesClient())

    _comments, metadata = scraper.scrape_youtube(
        'https://www.youtube.com/watch?v=dQw4w9WgXcQ', max_comments=10
    )

    assert metadata['like_count'] is None
    assert metadata['view_count'] == 100


class TestYouTubeErrorReason:

    def test_extracts_the_structured_reason_from_a_google_error_body(self):
        exc = _http_error(403, 'commentsDisabled')
        assert scraper._youtube_error_reason(exc) == 'commentsDisabled'

    def test_returns_empty_string_on_an_unparseable_body(self):
        exc = HttpError(httplib2.Response({'status': 500}), b'not json')
        assert scraper._youtube_error_reason(exc) == ''


class TestYouTubeRetry:
    """Avant ce correctif : vidéo privée, supprimée, commentaires désactivés
    et quota dépassé remontaient tous comme le même message générique, et
    une seule erreur réseau transitoire tuait la collecte immédiatement."""

    def test_retries_a_transient_error_and_succeeds(self, monkeypatch):
        monkeypatch.setattr(scraper.time, 'sleep', lambda _seconds: None)
        calls = []

        def flaky():
            calls.append(1)
            if len(calls) < 2:
                raise _http_error(503, 'backendError')
            return 'ok'

        assert scraper._call_youtube_with_retry(flaky, max_attempts=3) == 'ok'
        assert len(calls) == 2

    def test_does_not_retry_a_permanent_error_and_identifies_the_cause(self, monkeypatch):
        monkeypatch.setattr(scraper.time, 'sleep', lambda _seconds: None)
        calls = []

        def always_disabled():
            calls.append(1)
            raise _http_error(403, 'commentsDisabled')

        try:
            scraper._call_youtube_with_retry(always_disabled, max_attempts=3)
            assert False, "aurait dû lever YouTubeCollectionError"
        except scraper.YouTubeCollectionError as exc:
            assert exc.reason == 'commentsDisabled'
            assert 'désactivés' in str(exc)
        assert len(calls) == 1, "une erreur permanente ne doit jamais être rejouée"

    def test_gives_up_after_max_attempts_on_a_persistent_transient_error(self, monkeypatch):
        monkeypatch.setattr(scraper.time, 'sleep', lambda _seconds: None)
        calls = []

        def always_503():
            calls.append(1)
            raise _http_error(503, 'backendError')

        try:
            scraper._call_youtube_with_retry(always_503, max_attempts=3)
            assert False, "aurait dû lever YouTubeCollectionError après épuisement des tentatives"
        except scraper.YouTubeCollectionError:
            pass
        assert len(calls) == 3

    def test_quota_exceeded_is_identified_and_not_retried(self, monkeypatch):
        monkeypatch.setattr(scraper.time, 'sleep', lambda _seconds: None)
        calls = []

        def quota_hit():
            calls.append(1)
            raise _http_error(403, 'quotaExceeded')

        try:
            scraper._call_youtube_with_retry(quota_hit, max_attempts=3)
            assert False
        except scraper.YouTubeCollectionError as exc:
            assert exc.reason == 'quotaExceeded'
            assert 'quota' in str(exc).lower()
        assert len(calls) == 1


def test_scrape_youtube_surfaces_a_typed_error_when_comments_are_disabled(monkeypatch):
    """Bout-en-bout : la vraie fonction publique doit laisser passer l'erreur
    typée, pas la ravaler dans un message générique."""
    monkeypatch.setenv('YOUTUBE_API_KEY', 'test-key')
    monkeypatch.setattr(scraper.time, 'sleep', lambda _seconds: None)

    class _FailingExecutable:
        def execute(self):
            raise _http_error(403, 'commentsDisabled')

    class _CommentsDisabledClient(_FakeYouTubeClient):
        def list(self, **kwargs):
            if 'videoId' in kwargs:
                return _FailingExecutable()
            return super().list(**kwargs)

    monkeypatch.setattr(scraper, 'build', lambda *a, **k: _CommentsDisabledClient())

    try:
        scraper.scrape_youtube('https://www.youtube.com/watch?v=dQw4w9WgXcQ', max_comments=10)
        assert False, "aurait dû lever YouTubeCollectionError"
    except scraper.YouTubeCollectionError as exc:
        assert exc.reason == 'commentsDisabled'


class TestYouTubeNetworkFailure:
    """Le 13/09/2026, une connexion à l'API YouTube a expiré (socket.timeout) :
    ce n'est pas un HttpError, donc ni rejoué ni expliqué — l'écran affichait
    « Erreur lors de l'analyse. Réessayez dans quelques instants. »"""

    def test_retries_a_network_timeout_and_succeeds(self, monkeypatch):
        import socket
        monkeypatch.setattr(scraper.time, 'sleep', lambda _seconds: None)
        calls = []

        def flaky():
            calls.append(1)
            if len(calls) < 2:
                raise socket.timeout('timed out')
            return 'ok'

        assert scraper._call_youtube_with_retry(flaky, max_attempts=3) == 'ok'
        assert len(calls) == 2

    def test_persistent_network_failure_becomes_an_explained_error(self, monkeypatch):
        import socket
        monkeypatch.setattr(scraper.time, 'sleep', lambda _seconds: None)
        calls = []

        def always_timeout():
            calls.append(1)
            raise socket.timeout('timed out')

        try:
            scraper._call_youtube_with_retry(always_timeout, max_attempts=3)
            assert False, "aurait dû lever YouTubeCollectionError"
        except scraper.YouTubeCollectionError as exc:
            assert exc.reason == 'network'
            assert 'ne répond pas' in str(exc)
        assert len(calls) == 3


def test_analyze_route_explains_a_youtube_failure_instead_of_a_generic_500(monkeypatch):
    """La route /analyze doit transmettre la cause YouTube (désactivés, réseau…)."""
    import app as _app
    import api.db as _db
    monkeypatch.setattr(_db, 'check_usage_limit', lambda uid, email=None: {'allowed': True})

    def client():
        c = _app.app.test_client()
        with c.session_transaction() as sess:
            sess['user_id'] = 'youtube-tester'
            sess['user_email'] = 'youtube@example.com'
        return c

    def desactives(_url, *a, **k):
        raise scraper.YouTubeCollectionError('commentsDisabled', "Les commentaires sont désactivés sur cette vidéo.")
    monkeypatch.setattr(_app, 'scrape_youtube', desactives)
    r = client().post('/analyze', json={
        'source': 'youtube', 'content': 'https://www.youtube.com/watch?v=dAdkGfsZXMg'})
    assert r.status_code == 400
    assert 'désactivés' in r.get_json()['error']

    def reseau(_url, *a, **k):
        raise scraper.YouTubeCollectionError('network', scraper._YOUTUBE_ERROR_MESSAGES['network'])
    monkeypatch.setattr(_app, 'scrape_youtube', reseau)
    r = client().post('/analyze', json={
        'source': 'youtube', 'content': 'https://www.youtube.com/watch?v=dAdkGfsZXMg'})
    assert r.status_code == 503
    assert 'ne répond pas' in r.get_json()['error']
