# ─── Gabriel — Une seule interface : la V2 ───────────────────────────────────
#
# Les pages historiques (V1) ne doivent plus s'afficher : on arrive toujours
# dans l'interface V2. Une seule exception, indispensable : le shell V2 charge
# lui-même certaines pages dans une iframe marquée « embedded=1 ». Sans cette
# exception, l'iframe se rechargerait à l'infini.
# Lancer : venv/bin/pytest tests/test_v1_hors_service.py -v

import os
import sys

os.environ['AUTH_ENABLED']       = 'true'
os.environ['FLASK_SECRET_KEY']   = 'test-secret-v1'
os.environ.setdefault('MISTRAL_API_KEY', 'test-key')
os.environ.setdefault('SUPABASE_URL', '')
os.environ.setdefault('SUPABASE_KEY', '')
os.environ['RATE_LIMIT_ENABLED'] = 'false'

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import app as _app

UID = 'uid-v1-hors-service'

# Page V1 → agent visé dans la V2.
PAGES_AGENTS = {
    '/psychologue': 'psychologue',
    '/stratege':    'stratege',
    '/createur':    'createur',
}


def _client():
    c = _app.app.test_client()
    with c.session_transaction() as s:
        s['user_id']    = UID
        s['user_email'] = f'{UID}@example.com'
        s['user_name']  = 'Testeur V1'
    return c


def test_les_pages_agents_v1_ne_s_affichent_plus():
    """Taper l'ancienne adresse ne montre plus la page V1 : on est renvoyé
    vers l'interface V2, sur le bon agent."""
    for route, agent in PAGES_AGENTS.items():
        r = _client().get(route)
        assert r.status_code == 302, f'{route} affiche encore la page V1'
        cible = r.headers['Location']
        assert cible.startswith('/orchestrateur'), f'{route} ne renvoie pas vers la V2'
        assert f'agent={agent}' in cible, f'{route} renvoie vers la V2 sans dire quel agent ouvrir'


def test_le_shell_v2_peut_toujours_charger_la_page_dans_son_iframe():
    """Le garde-fou : sans cette exception, l'iframe du shell V2 se
    rechargerait indéfiniment sur elle-même."""
    for route in PAGES_AGENTS:
        r = _client().get(f'{route}?embedded=1')
        assert r.status_code == 200, f'{route}?embedded=1 doit servir la page à l’iframe'


def test_l_ancienne_interface_a_onglets_mene_a_la_v2():
    r = _client().get('/app')
    assert r.status_code == 302
    assert r.headers['Location'] == '/orchestrateur'


def test_la_page_d_accueil_ne_renvoie_plus_vers_une_page_v1():
    """Un visiteur qui clique sur l'accueil doit entrer dans la V2, pas
    atterrir dans l'ancienne interface Dossiers."""
    corps = _app.app.test_client().get('/').get_data(as_text=True)
    assert 'href="/dossiers"' not in corps, 'L’accueil renvoie encore vers une page V1'
    assert 'href="/orchestrateur"' in corps


def test_la_page_dossiers_v1_ne_s_affiche_plus():
    """Elle ne savait que lister, créer et supprimer — la V2 fait les trois
    dans sa navigation, avec les mêmes appels."""
    r = _client().get('/dossiers')
    assert r.status_code == 302
    assert r.headers['Location'] == '/orchestrateur'


def test_un_lien_vers_un_dossier_precis_rouvre_ce_dossier(monkeypatch):
    """Un favori ou un lien partagé doit rouvrir le bon dossier dans la V2,
    pas celui consulté auparavant.

    Le dossier est simulé plutôt que réellement créé : sans Supabase, le
    stockage ne le relit pas, et le test mesurerait alors le stockage au lieu
    de la redirection."""
    fid = 'dossier-lien-direct'
    monkeypatch.setattr(_app._db, 'get_folder_by_id',
                        lambda folder_id, uid=None: {'folder_id': folder_id, 'title': 'Dossier de test'})
    c = _client()
    r = c.get(f'/dossiers/{fid}')
    assert r.status_code == 302
    assert f'folder_id={fid}' in r.headers['Location'], 'le dossier visé est perdu en chemin'
    with c.session_transaction() as s:
        assert s.get('active_folder_id') == fid


def test_un_dossier_introuvable_ne_renvoie_pas_vers_la_v1():
    r = _client().get('/dossiers/inexistant-xyz')
    assert r.status_code == 302
    assert '/dossiers' not in r.headers['Location']


def test_mes_analyses_ne_s_affiche_plus():
    r = _client().get('/mes-analyses')
    assert r.status_code == 302
    assert r.headers['Location'] == '/orchestrateur'


def test_mes_strategies_ne_s_affiche_plus():
    r = _client().get('/mes-strategies')
    assert r.status_code == 302
    assert r.headers['Location'] == '/orchestrateur'


def test_historique_ne_s_affiche_plus():
    r = _client().get('/historique')
    assert r.status_code == 302
    assert r.headers['Location'] == '/orchestrateur'


def test_ouvrir_une_analyse_orpheline_l_adopte_dans_un_dossier(monkeypatch):
    """Une analyse d'avant les dossiers (aucun folder_id) doit rester
    atteignable — sans dossier auto-créé pour la recevoir, elle deviendrait
    définitivement hors d'atteinte une fois la page d'historique disparue."""
    monkeypatch.setattr(_app._db, 'get_analysis_by_id',
                        lambda aid, uid=None: {'analysis_id': aid, 'title': 'Vieille analyse', 'folder_id': ''})
    créés = {}
    monkeypatch.setattr(_app._db, 'create_folder',
                        lambda fid, uid, title, **kw: créés.setdefault('folder_id', fid) or {'folder_id': fid})
    lié = {}
    monkeypatch.setattr(_app._db, 'update_folder',
                        lambda fid, uid, **kw: lié.update(kw))
    r = _client().get('/history/vieille-analyse/open')
    assert r.status_code == 302
    assert 'agent=psychologue' in r.headers['Location']
    assert créés['folder_id'] in r.headers['Location']
    assert lié.get('analysis_id') == 'vieille-analyse'


def test_ouvrir_une_analyse_deja_dans_un_dossier_ne_cree_rien(monkeypatch):
    """Le cas courant : l'analyse a déjà un dossier, on ne doit pas en créer
    un second."""
    monkeypatch.setattr(_app._db, 'get_analysis_by_id',
                        lambda aid, uid=None: {'analysis_id': aid, 'folder_id': 'dossier-existant'})
    def _pas_dappel(*a, **k): raise AssertionError('create_folder ne devrait pas être appelé')
    monkeypatch.setattr(_app._db, 'create_folder', _pas_dappel)
    r = _client().get('/history/aid-1/open')
    assert r.status_code == 302
    assert 'folder_id=dossier-existant' in r.headers['Location']


def test_ouvrir_une_analyse_introuvable_ne_plante_pas(monkeypatch):
    monkeypatch.setattr(_app._db, 'get_analysis_by_id', lambda aid, uid=None: None)
    r = _client().get('/history/inexistante/open')
    assert r.status_code == 302
    assert r.headers['Location'] == '/orchestrateur'


def test_ouvrir_une_strategie_orpheline_l_adopte_dans_un_dossier(monkeypatch):
    monkeypatch.setattr(_app._db, 'get_strategy_by_id',
                        lambda sid, uid=None: {'strategy_id': sid, 'folder_id': ''})
    créés = {}
    monkeypatch.setattr(_app._db, 'create_folder',
                        lambda fid, uid, title, **kw: créés.setdefault('folder_id', fid) or {'folder_id': fid})
    monkeypatch.setattr(_app._db, 'update_folder', lambda fid, uid, **kw: True)
    r = _client().get('/strategies/vieille-strategie/open')
    assert r.status_code == 302
    assert 'agent=stratege' in r.headers['Location']
    assert créés['folder_id'] in r.headers['Location']


def test_un_folder_id_survit_a_la_redirection_de_mes_analyses():
    r = _client().get('/mes-analyses?folder_id=fid-abc')
    assert r.status_code == 302
    assert 'folder_id=fid-abc' in r.headers['Location']


def test_upgrade_ne_s_affiche_plus():
    """Les trois offres vivent dans le panneau Paramètres de la V2."""
    r = _client().get('/upgrade')
    assert r.status_code == 302
    assert r.headers['Location'] == '/orchestrateur?section=settings'


def test_retour_stripe_reussi_ramene_vers_les_parametres():
    r = _client().get('/stripe/success?session_id=cs_test_123')
    assert r.status_code == 302
    assert r.headers['Location'] == '/orchestrateur?section=settings'


def test_csp_autorise_la_lecture_audio_en_blob():
    """La lecture vocale de l'Entretien stratégique (POST /voice/speak, voir
    StrategeView.jsx) charge l'audio via new Audio(URL.createObjectURL(blob)) :
    sans media-src incluant blob:, Chrome bloque la lecture en silence même
    sous 'self' — trouvé en testant réellement dans le navigateur, jamais en
    Vitest (jsdom n'applique aucune CSP)."""
    r = _client().get('/')
    csp = r.headers.get('Content-Security-Policy', '')
    assert "media-src" in csp
    assert "blob:" in csp.split("media-src")[1].split(";")[0]


def test_identite_dev_local_obtient_sa_ligne_gabriel_users(monkeypatch):
    """Sans cette ligne, la déduction de crédits en local (AUTH_ENABLED=false)
    s'exécute sans erreur mais ne change jamais rien — trouvé en vérifiant le
    solde après une génération de stratégie réussie en conditions réelles."""
    import api.auth as _auth

    monkeypatch.setenv('AUTH_ENABLED', 'false')
    monkeypatch.setenv('GABRIEL_ENV', 'development')
    monkeypatch.delenv('RENDER', raising=False)
    monkeypatch.delenv('RENDER_EXTERNAL_URL', raising=False)

    class _FakeTable:
        def __init__(self, store):
            self.store = store
            self._filter = None

        def select(self, *_a, **_k): return self
        def eq(self, key, value):
            self._filter = (key, value)
            return self
        def limit(self, *_a, **_k): return self
        def insert(self, row):
            self.store.append(row)
            return self
        def execute(self):
            if self._filter and self._filter[0] == 'user_id':
                matches = [r for r in self.store if r.get('user_id') == self._filter[1]]
                return type('R', (), {'data': matches})()
            return type('R', (), {'data': self.store})()

    class _FakeSupabase:
        def __init__(self): self.rows = []
        def table(self, _name): return _FakeTable(self.rows)

    fake = _FakeSupabase()
    monkeypatch.setattr(_auth, '_supabase', fake)
    monkeypatch.setattr(_auth, '_dev_user_provisioned', False)

    _auth._ensure_dev_user_row()
    assert len(fake.rows) == 1
    assert fake.rows[0]['user_id'] == _auth._DEV_USER['user_id']
    assert 'credits' not in fake.rows[0]  # vient du DEFAULT Supabase, jamais envoyé

    # Un second appel (déjà provisionné) ne recrée pas la ligne.
    _auth._ensure_dev_user_row()
    assert len(fake.rows) == 1


def test_provisionnement_dev_ne_recree_pas_une_ligne_existante(monkeypatch):
    import api.auth as _auth

    monkeypatch.setenv('AUTH_ENABLED', 'false')
    monkeypatch.setenv('GABRIEL_ENV', 'development')
    monkeypatch.delenv('RENDER', raising=False)
    monkeypatch.delenv('RENDER_EXTERNAL_URL', raising=False)

    class _FakeTable:
        def __init__(self, store):
            self.store = store
        def select(self, *_a, **_k): return self
        def eq(self, *_a, **_k): return self
        def limit(self, *_a, **_k): return self
        def insert(self, row): raise AssertionError('ne devrait jamais insérer — la ligne existe déjà')
        def execute(self): return type('R', (), {'data': [{'user_id': _auth._DEV_USER['user_id']}]})()

    class _FakeSupabase:
        def table(self, _name): return _FakeTable([])

    monkeypatch.setattr(_auth, '_supabase', _FakeSupabase())
    monkeypatch.setattr(_auth, '_dev_user_provisioned', False)
    _auth._ensure_dev_user_row()  # ne doit pas lever
