"""Équivalence et contrat des outils de collecte et de fichiers.

Le premier outil qui touche le réseau. La preuve attendue n'est pas
seulement « même sortie » mais « le contrat réseau (timeout, erreurs
typées, pas de faux cache) est correctement déclaré et non altéré » —
c'est justement ce que le brief demande de vérifier pour tout Tool externe.
"""

import io

import pytest

import tools as tools_pkg
from services.scraper import YouTubeCollectionError


class _FakeExecute:
    def __init__(self, payload):
        self._payload = payload

    def execute(self):
        return self._payload


class _FakeYoutubeClient:
    """Simule assez de l'API YouTube pour scrape_youtube — aucun réseau réel."""

    def __init__(self, comments_payload, video_payload):
        self._comments_payload = comments_payload
        self._video_payload = video_payload

    def videos(self):
        return self

    def list(self, **kw):
        return _FakeExecute(self._video_payload)

    def commentThreads(self):
        return self


class TestCollectionYouTube:
    VIDEO_PAYLOAD = {'items': [{
        'snippet': {'title': 'Comment structurer son offre', 'channelTitle': 'Gabriel',
                    'description': 'd', 'publishedAt': '2024-01-01'},
        'statistics': {'viewCount': '1000', 'likeCount': '50', 'commentCount': '2'},
        'contentDetails': {'duration': 'PT4M13S'},
    }]}

    def _commentThreads_list(self, **kw):
        payload = {'items': [
            {'snippet': {
                'topLevelComment': {'id': 'c1', 'snippet': {
                    'textDisplay': 'Merci beaucoup', 'likeCount': 12,
                    'authorDisplayName': 'A', 'publishedAt': '2024-01-02',
                    'updatedAt': '2024-01-02'}},
                'totalReplyCount': 0}},
            {'snippet': {
                'topLevelComment': {'id': 'c2', 'snippet': {
                    'textDisplay': 'Pas convaincu', 'likeCount': 3,
                    'authorDisplayName': 'B', 'publishedAt': '2024-01-03',
                    'updatedAt': '2024-01-03'}},
                'totalReplyCount': 0}},
        ]}
        return _FakeExecute(payload)

    def _patch_build(self, monkeypatch, module):
        client = _FakeYoutubeClient(None, self.VIDEO_PAYLOAD)
        client.list = self._commentThreads_list if False else client.list
        # `videos().list` doit rendre VIDEO_PAYLOAD, `commentThreads().list` la
        # page de commentaires : deux comportements différents pour `.list`.
        call_count = {'n': 0}

        def list_dispatch(**kw):
            call_count['n'] += 1
            if 'part' in kw and kw.get('part') == 'snippet,statistics,contentDetails':
                return _FakeExecute(self.VIDEO_PAYLOAD)
            return self._commentThreads_list(**kw)

        client.list = list_dispatch
        client.commentThreads = lambda: client
        monkeypatch.setattr(module, 'build', lambda *a, **k: client)
        monkeypatch.setenv('YOUTUBE_API_KEY', 'fake-key-for-tests')

    def test_l_outil_rend_ce_que_scrape_youtube_rend(self, monkeypatch):
        import services.scraper as scraper
        self._patch_build(monkeypatch, scraper)

        attendu_comments, attendu_info = scraper.scrape_youtube(
            'https://youtube.com/watch?v=dQw4w9WgXcQ', max_comments=10)

        obtenu = tools_pkg.registry.get('collection.fetch_youtube_comments').run(
            url_or_id='https://youtube.com/watch?v=dQw4w9WgXcQ', max_comments=10)

        assert obtenu['comments'] == attendu_comments
        assert obtenu['video_info'] == attendu_info

    def test_les_deux_sorties_sont_nommees_et_non_en_tuple(self, monkeypatch):
        """`scrape_youtube` rend un tuple : l'outil doit nommer ses deux
        sorties plutôt que forcer l'appelant à connaître l'ordre."""
        import services.scraper as scraper
        self._patch_build(monkeypatch, scraper)
        obtenu = tools_pkg.registry.get('collection.fetch_youtube_comments').run(
            url_or_id='https://youtube.com/watch?v=dQw4w9WgXcQ')
        assert set(obtenu) == {'comments', 'video_info'}

    def test_une_erreur_youtube_typee_traverse_l_outil_sans_etre_generique(self, monkeypatch):
        """La taxonomie d'erreurs (reason: commentsDisabled, quotaExceeded…)
        doit survivre au passage par l'outil — la remplacer par un ToolError
        générique effacerait ce que services/scraper.py distingue déjà."""
        import services.scraper as scraper

        def _casse(*a, **k):
            raise YouTubeCollectionError('commentsDisabled',
                                         "Les commentaires sont désactivés sur cette vidéo.")

        monkeypatch.setattr(scraper, 'scrape_youtube', _casse)
        with pytest.raises(YouTubeCollectionError) as exc:
            tools_pkg.registry.get('collection.fetch_youtube_comments').run(
                url_or_id='https://youtube.com/watch?v=x')
        assert exc.value.reason == 'commentsDisabled'

    def test_le_contrat_declare_lhonnetete_sur_le_cache(self):
        """Des commentaires évoluent entre deux appels : les mettre en cache
        servirait des données périmées sans le dire."""
        spec = tools_pkg.registry.get('collection.fetch_youtube_comments').spec
        assert spec.cacheable is False
        assert spec.deterministic is False

    def test_le_contrat_declare_un_timeout_et_un_cout(self):
        spec = tools_pkg.registry.get('collection.fetch_youtube_comments').spec
        assert spec.timeout_s == 15
        assert spec.cost_hint  # un outil réseau facturé ne doit jamais taire son coût

    def test_le_contrat_se_declare_parallelisable(self):
        """Chaque appel ouvre son propre client API : aucun état partagé."""
        assert tools_pkg.registry.get(
            'collection.fetch_youtube_comments').spec.parallel_safe is True


class TestFichiersDeCommentaires:
    CSV = "text,likes\nMerci beaucoup,12\nPas convaincu du tout,3\n".encode('utf-8')

    def test_l_outil_rend_ce_que_la_chaine_reelle_rend(self):
        from services.file_importer import normalize_comment_items, parse_comments_file

        parsed = parse_comments_file('avis.csv', self.CSV)
        attendu = normalize_comment_items(parsed['items'], source_file='avis.csv')

        obtenu = tools_pkg.registry.get('files.parse_comments').run(
            filename='avis.csv', raw_bytes=self.CSV)

        assert obtenu['items'] == attendu
        assert obtenu['file_type'] == 'csv'

    def test_un_format_non_supporte_leve_lerreur_typee_dorigine(self):
        from services.file_importer import FileImportError
        with pytest.raises(FileImportError, match='Format non supporté'):
            tools_pkg.registry.get('files.parse_comments').run(
                filename='malware.exe', raw_bytes=b'x')

    def test_un_fichier_sans_colonne_de_commentaire_leve_une_erreur_claire(self):
        from services.file_importer import FileImportError
        csv_sans_texte = "id,valeur\n1,100\n".encode('utf-8')
        with pytest.raises(FileImportError, match='Aucune colonne'):
            tools_pkg.registry.get('files.parse_comments').run(
                filename='data.csv', raw_bytes=csv_sans_texte)

    def test_le_contrat_se_declare_pur_et_cacheable(self):
        """Mêmes octets, même fichier → même résultat : rien n'empêche de
        réutiliser une lecture déjà faite."""
        spec = tools_pkg.registry.get('files.parse_comments').spec
        assert spec.deterministic is True
        assert spec.cacheable is True
        assert spec.timeout_s is None   # local, aucun réseau
