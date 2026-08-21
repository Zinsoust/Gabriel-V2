"""Collecte Instagram et TikTok — cinq situations, cinq réponses distinctes.

Défaut d'origine : ces collecteurs renvoyaient `([], {})` pour la clé
absente, le lien non reconnu, l'API en panne, l'échec réseau, et l'absence
réelle de commentaires. L'utilisateur recevait un écran vide sans savoir
s'il devait corriger son lien ou réessayer plus tard.

Un seul de ces cas mérite un retour vide : la collecte a réussi et la
publication n'a pas de commentaire.
"""

import pytest

import services.scraper as scraper
from services.scraper import SocialCollectionError


LIEN_IG = 'https://www.instagram.com/p/Cabc123/'
LIEN_TT = 'https://www.tiktok.com/@auteur/video/7123456789'


class _Reponse:
    def __init__(self, code, payload=None):
        self.status_code = code
        self._payload = payload or {}

    def json(self):
        return self._payload


class TestInstagram:
    def test_sans_cle_api_sur_un_lien_la_cause_est_nommee(self, monkeypatch):
        monkeypatch.delenv('RAPIDAPI_KEY', raising=False)
        with pytest.raises(SocialCollectionError) as exc:
            scraper.scrape_instagram_rapidapi(LIEN_IG)
        assert exc.value.reason == 'apiKeyMissing'
        assert exc.value.platform == 'instagram'

    def test_un_lien_non_reconnu_est_distingue_dune_panne(self, monkeypatch):
        """Corriger son lien et réessayer plus tard sont deux actions
        différentes : l'utilisateur doit savoir laquelle le concerne."""
        monkeypatch.setenv('RAPIDAPI_KEY', 'clé-de-test')
        with pytest.raises(SocialCollectionError) as exc:
            scraper.scrape_instagram_rapidapi('https://www.instagram.com/uncompte/')
        assert exc.value.reason == 'invalidUrl'

    def test_une_api_en_panne_est_signalee(self, monkeypatch):
        monkeypatch.setenv('RAPIDAPI_KEY', 'clé-de-test')
        monkeypatch.setattr(scraper.requests, 'get',
                            lambda *a, **k: _Reponse(500))
        with pytest.raises(SocialCollectionError) as exc:
            scraper.scrape_instagram_rapidapi(LIEN_IG)
        assert exc.value.reason == 'apiError'

    def test_un_echec_reseau_est_signale(self, monkeypatch):
        monkeypatch.setenv('RAPIDAPI_KEY', 'clé-de-test')

        def _casse(*a, **k):
            raise ConnectionError('réseau injoignable')

        monkeypatch.setattr(scraper.requests, 'get', _casse)
        with pytest.raises(SocialCollectionError) as exc:
            scraper.scrape_instagram_rapidapi(LIEN_IG)
        assert exc.value.reason == 'apiError'

    def test_une_publication_sans_commentaire_rend_bien_un_vide(self, monkeypatch):
        """Le seul cas qui mérite un retour vide : la collecte a réussi."""
        monkeypatch.setenv('RAPIDAPI_KEY', 'clé-de-test')
        monkeypatch.setattr(scraper.requests, 'get',
                            lambda *a, **k: _Reponse(200, {'data': {'items': []}}))
        assert scraper.scrape_instagram_rapidapi(LIEN_IG) == ([], {})

    def test_les_commentaires_sont_bien_collectes(self, monkeypatch):
        monkeypatch.setenv('RAPIDAPI_KEY', 'clé-de-test')
        monkeypatch.setattr(scraper.requests, 'get', lambda *a, **k: _Reponse(200, {
            'data': {'items': [
                {'text': 'Super contenu', 'comment_like_count': 12,
                 'user': {'username': 'alice'}},
                {'text': '   ', 'comment_like_count': 0, 'user': {}},
            ]}}))
        commentaires, _ = scraper.scrape_instagram_rapidapi(LIEN_IG)
        assert len(commentaires) == 1      # le vide est écarté
        assert commentaires[0] == {'text': 'Super contenu', 'likes': 12, 'author': 'alice'}

    def test_le_401_garde_son_erreur_dediee(self, monkeypatch):
        """`RapidAPIUnavailable` existait déjà et portait un message adapté
        (clé valide mais non abonnée) : elle ne doit pas être absorbée."""
        monkeypatch.setenv('RAPIDAPI_KEY', 'clé-de-test')
        monkeypatch.setattr(scraper.requests, 'get', lambda *a, **k: _Reponse(403))
        with pytest.raises(scraper.RapidAPIUnavailable):
            scraper.scrape_instagram_rapidapi(LIEN_IG)


class TestCollageManuelPreserve:
    """Le chemin à ne pas casser : coller des commentaires bruts en choisissant
    la source Instagram ou TikTok fonctionne aujourd'hui, même sans clé API.
    Lever une erreur sur du texte libre le briserait."""

    TEXTE = "Super vidéo\nPas convaincu\nLe prix me freine"

    @pytest.mark.parametrize('collecteur', ['scrape_instagram_rapidapi',
                                            'scrape_tiktok_rapidapi'])
    def test_du_texte_libre_ne_leve_jamais(self, monkeypatch, collecteur):
        monkeypatch.delenv('RAPIDAPI_KEY', raising=False)
        commentaires, _ = getattr(scraper, collecteur)(self.TEXTE)
        assert commentaires == []

    @pytest.mark.parametrize('collecteur', ['scrape_instagram_rapidapi',
                                            'scrape_tiktok_rapidapi'])
    def test_du_texte_libre_ne_leve_pas_non_plus_avec_une_cle(self, monkeypatch,
                                                              collecteur):
        monkeypatch.setenv('RAPIDAPI_KEY', 'clé-de-test')
        commentaires, _ = getattr(scraper, collecteur)(self.TEXTE)
        assert commentaires == []


class TestTikTok:
    def test_sans_cle_api_sur_un_lien_la_cause_est_nommee(self, monkeypatch):
        monkeypatch.delenv('RAPIDAPI_KEY', raising=False)
        with pytest.raises(SocialCollectionError) as exc:
            scraper.scrape_tiktok_rapidapi(LIEN_TT)
        assert exc.value.reason == 'apiKeyMissing'
        assert exc.value.platform == 'tiktok'

    def test_un_lien_sans_identifiant_video_est_refuse(self, monkeypatch):
        monkeypatch.setenv('RAPIDAPI_KEY', 'clé-de-test')
        monkeypatch.setattr(scraper.requests, 'get', lambda *a, **k: _Reponse(200, {}))
        with pytest.raises(SocialCollectionError) as exc:
            scraper.scrape_tiktok_rapidapi('https://www.tiktok.com/@auteur')
        assert exc.value.reason == 'invalidUrl'

    def test_un_echec_au_premier_appel_de_commentaires_est_signale(self, monkeypatch):
        monkeypatch.setenv('RAPIDAPI_KEY', 'clé-de-test')

        def _get(url, **k):
            if 'comment/list' in url:
                return _Reponse(500)
            return _Reponse(200, {'data': {'itemInfo': {'itemStruct': {
                'desc': 'Titre', 'author': {'uniqueId': 'auteur'}, 'id': '7123456789'}}}})

        monkeypatch.setattr(scraper.requests, 'get', _get)
        with pytest.raises(SocialCollectionError) as exc:
            scraper.scrape_tiktok_rapidapi(LIEN_TT)
        assert exc.value.reason == 'apiError'

    def test_un_echec_en_cours_de_pagination_garde_ce_qui_est_collecte(self, monkeypatch):
        """Distinction qui compte : échouer au premier appel ne rend rien,
        s'arrêter en cours de route garde le travail déjà fait."""
        monkeypatch.setenv('RAPIDAPI_KEY', 'clé-de-test')
        appels = {'n': 0}

        def _get(url, **k):
            if 'comment/list' not in url:
                return _Reponse(200, {'data': {'itemInfo': {'itemStruct': {
                    'desc': 'T', 'author': {'uniqueId': 'a'}, 'id': '7123456789'}}}})
            appels['n'] += 1
            if appels['n'] == 1:
                return _Reponse(200, {'data': {
                    'comments': [{'text': 'Premier lot', 'digg_count': 5,
                                  'user': {'unique_id': 'bob'}}],
                    'has_more': True, 'cursor': 50}})
            return _Reponse(500)      # la suite tombe

        monkeypatch.setattr(scraper.requests, 'get', _get)
        commentaires, info = scraper.scrape_tiktok_rapidapi(LIEN_TT)
        assert len(commentaires) == 1
        assert commentaires[0]['text'] == 'Premier lot'
        assert info['title'] == 'T'


class TestOutilsDeCollecteSociale:
    """Une fois le modèle d'erreur clarifié, ces capacités pouvaient être
    déclarées — c'est ce que l'audit conditionnait à cette correction."""

    def test_loutil_instagram_rend_ce_que_le_collecteur_rend(self, monkeypatch):
        import tools as tools_pkg

        monkeypatch.setenv('RAPIDAPI_KEY', 'clé-de-test')
        monkeypatch.setattr(scraper.requests, 'get', lambda *a, **k: _Reponse(200, {
            'data': {'items': [{'text': 'Super', 'comment_like_count': 3,
                                'user': {'username': 'alice'}}]}}))

        attendu, info = scraper.scrape_instagram_rapidapi(LIEN_IG)
        obtenu = tools_pkg.registry.get('collection.fetch_instagram_comments').run(
            url=LIEN_IG)
        assert obtenu == {'comments': attendu, 'post_info': info}

    def test_lerreur_typee_traverse_loutil_sans_etre_generique(self, monkeypatch):
        """Comme pour YouTube : la cause doit survivre au passage par l'outil,
        sinon l'utilisateur reperd le diagnostic qu'on vient de lui rendre."""
        import tools as tools_pkg

        monkeypatch.delenv('RAPIDAPI_KEY', raising=False)
        with pytest.raises(SocialCollectionError) as exc:
            tools_pkg.registry.get('collection.fetch_tiktok_comments').run(url=LIEN_TT)
        assert exc.value.reason == 'apiKeyMissing'

    def test_les_contrats_declarent_leur_cout_et_leur_timeout(self):
        """Un outil réseau facturé ne doit jamais taire son coût — et celui de
        TikTok n'est pas d'une requête par vidéo."""
        import tools as tools_pkg

        for tool_id in ('collection.fetch_instagram_comments',
                        'collection.fetch_tiktok_comments'):
            spec = tools_pkg.registry.get(tool_id).spec
            assert spec.timeout_s == 15
            assert spec.cost_hint
            assert spec.cacheable is False      # données vivantes
            assert spec.deterministic is False

    def test_le_cout_tiktok_declare_sa_pagination(self):
        import tools as tools_pkg
        cout = tools_pkg.registry.get('collection.fetch_tiktok_comments').spec.cost_hint
        assert '2 requêtes' in cout and 'page' in cout
