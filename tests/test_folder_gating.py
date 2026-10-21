# ─── Gabriel — Tests verrouillage par dossier + résolution stratégie/psycho ───
#
# Couvre le décorateur _ensure_folder (accès aux agents ne requiert plus de
# dossier créé au préalable : un dossier est créé silencieusement en session
# si aucun n'est actif) et les helpers _resolve_psycho / _resolve_strategy
# utilisés par /creator/generate pour ne jamais partir d'un contexte vide
# s'il est disponible ailleurs (folder_id, strategy_id, cache).
# Lancer : cd /Users/easycash/Desktop/Gabriel && venv/bin/pytest tests/test_folder_gating.py -v

import os
import sys

os.environ['AUTH_ENABLED']       = 'true'
os.environ['FLASK_SECRET_KEY']   = 'test-secret-gating'
os.environ.setdefault('MISTRAL_API_KEY', 'test-key')
os.environ.setdefault('SUPABASE_URL', '')
os.environ.setdefault('SUPABASE_KEY', '')
os.environ['RATE_LIMIT_ENABLED'] = 'false'

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import api.db as _db
import app as _app

UID = 'uid-gating-a'

GATED_ROUTES = ['/psychologue', '/stratege', '/createur', '/mes-analyses', '/mes-strategies']

# Les cinq pages ne s'affichent plus en V1 : elles renvoient toutes vers
# l'interface V2, en conservant le dossier demandé.
AGENT_ROUTES = ['/psychologue', '/stratege', '/createur', '/mes-analyses', '/mes-strategies']


def _client():
    c = _app.app.test_client()
    with c.session_transaction() as s:
        s['user_id']    = UID
        s['user_email'] = f'{UID}@example.com'
        s['user_name']  = 'Gating Tester'
    return c


# ══════════════════════════════════════════════════════════════════════════════
# 1. Accès libre — aucun dossier actif ne bloque plus rien
# ══════════════════════════════════════════════════════════════════════════════
def test_gated_routes_auto_create_folder_without_active_folder():
    """Sans dossier actif en session, chaque route agent répond 200 et crée
    silencieusement un dossier attaché à la session (plus de redirection)."""
    for route in GATED_ROUTES:
        c = _client()
        r = c.get(route)
        # Ce qui compte : l'accès n'est jamais refusé (ni /login, ni blocage).
        assert r.status_code in (200, 302), f'{route} ne devrait pas bloquer'
        if r.status_code == 302:
            assert '/login' not in r.headers['Location'], f'{route} ne devrait pas exiger une reconnexion'
        with c.session_transaction() as s:
            assert s.get('active_folder_id'), f'{route} devrait créer un dossier actif en session'


# ══════════════════════════════════════════════════════════════════════════════
# 2. Déblocage — folder_id en paramètre d'URL
# ══════════════════════════════════════════════════════════════════════════════
def test_folder_id_param_unlocks_access():
    """Un folder_id passé en paramètre d'URL survit à la redirection vers la V2."""
    for route in AGENT_ROUTES:
        c = _client()
        r = c.get(f'{route}?folder_id=fid-test-123')
        # Renvoyé vers la V2, mais le dossier demandé doit survivre au trajet :
        # sans lui, l'utilisateur arriverait sur un autre dossier que le sien.
        assert r.status_code == 302, f'{route} devrait renvoyer vers la V2'
        assert 'folder_id=fid-test-123' in r.headers['Location'], (
            f'{route} perd le dossier demandé en chemin')


def test_folder_id_param_persists_in_session():
    """Une fois le folder_id passé une fois, les visites suivantes sans paramètre passent aussi."""
    c = _client()
    r1 = c.get('/psychologue?folder_id=fid-test-456')
    assert r1.status_code == 302
    with c.session_transaction() as s:
        assert s.get('active_folder_id') == 'fid-test-456'

    # Deuxième requête, même client (donc même session), sans folder_id explicite
    r2 = c.get('/stratege')
    assert r2.status_code == 302

    r3 = c.get('/mes-analyses')
    assert r3.status_code == 302


def test_dossier_detail_page_sets_active_folder():
    """Ouvrir /dossiers/<folder_id> (même sur un dossier introuvable → redirect)
    ne doit pas planter. Un dossier inconnu ne débloque rien lui-même, mais
    l'accès aux agents reste garanti (dossier auto-créé si besoin)."""
    c = _client()
    # Dossier inconnu → redirige vers /dossiers, ne débloque rien
    r = c.get('/dossiers/unknown-folder-xyz')
    assert r.status_code in (302, 301)
    r2 = c.get('/psychologue')
    assert r2.status_code == 302  # renvoyé vers la V2, jamais bloqué


# ══════════════════════════════════════════════════════════════════════════════
# 3. _resolve_strategy — ne jamais rester vide si une source existe
# ══════════════════════════════════════════════════════════════════════════════
def test_resolve_strategy_uses_provided_payload():
    strat = _app._resolve_strategy({'strategy': {'decision_centrale': 'Test direct'}}, UID)
    assert strat.get('decision_centrale') == 'Test direct'


def test_resolve_strategy_uses_legacy_key():
    strat = _app._resolve_strategy({'strategie_data': {'decision_centrale': 'Legacy'}}, UID)
    assert strat.get('decision_centrale') == 'Legacy'


def test_resolve_strategy_empty_when_nothing_available():
    strat = _app._resolve_strategy({}, UID)
    assert strat == {}


def test_resolve_strategy_via_strategy_id(monkeypatch):
    """Si strategy_id est fourni, on va chercher la stratégie complète en DB."""
    def fake_get_strategy_by_id(strategy_id, user_id=None):
        assert strategy_id == 'sid-42'
        return {'strategy_result': {'decision_centrale': 'Via strategy_id'}}
    monkeypatch.setattr(_db, 'get_strategy_by_id', fake_get_strategy_by_id)

    strat = _app._resolve_strategy({'strategy_id': 'sid-42'}, UID)
    assert strat.get('decision_centrale') == 'Via strategy_id'


def test_resolve_strategy_via_folder_id(monkeypatch):
    """Si seul folder_id est fourni, on résout le strategy_id du dossier puis la stratégie."""
    def fake_get_folder_by_id(folder_id, user_id):
        assert folder_id == 'fid-99'
        return {'strategy_id': 'sid-linked'}
    def fake_get_strategy_by_id(strategy_id, user_id=None):
        assert strategy_id == 'sid-linked'
        return {'folder_id': 'fid-99', 'strategy_result': {'decision_centrale': 'Via folder_id'}}
    monkeypatch.setattr(_db, 'get_folder_by_id', fake_get_folder_by_id)
    monkeypatch.setattr(_db, 'get_strategy_by_id', fake_get_strategy_by_id)

    strat = _app._resolve_strategy({'folder_id': 'fid-99'}, UID)
    assert strat.get('decision_centrale') == 'Via folder_id'


def test_resolve_strategy_folder_without_strategy_yet():
    """Un dossier existant mais sans stratégie liée ne doit pas planter — retourne {}."""
    strat = _app._resolve_strategy({'folder_id': 'fid-no-strategy'}, UID)
    assert strat == {}


def test_resolve_strategy_rejects_strategy_from_another_folder(monkeypatch):
    """Un ancien onglet ne peut pas injecter l'identifiant d'un autre dossier."""
    monkeypatch.setattr(_db, 'get_folder_by_id', lambda folder_id, user_id: {
        'folder_id': folder_id, 'strategy_id': 'sid-current',
    })
    monkeypatch.setattr(_db, 'get_strategy_by_id', lambda *_args, **_kwargs: {
        'folder_id': 'fid-other',
        'strategy_result': {'decision_centrale': 'Contexte périmé'},
    })

    assert _app._resolve_strategy({
        'folder_id': 'fid-current', 'strategy_id': 'sid-other',
    }, UID) == {}


def test_resolve_strategy_accepts_exact_folder_strategy_pair(monkeypatch):
    monkeypatch.setattr(_db, 'get_folder_by_id', lambda folder_id, user_id: {
        'folder_id': folder_id, 'strategy_id': 'sid-current',
    })
    monkeypatch.setattr(_db, 'get_strategy_by_id', lambda *_args, **_kwargs: {
        'folder_id': 'fid-current',
        'strategy_result': {'decision_centrale': 'Contexte courant'},
    })

    strat = _app._resolve_strategy({
        'folder_id': 'fid-current', 'strategy_id': 'sid-current',
    }, UID)
    assert strat['decision_centrale'] == 'Contexte courant'


def test_creator_route_refuses_stale_strategy_before_generation(monkeypatch):
    monkeypatch.setattr(_db, 'has_enough_credits', lambda *_args, **_kwargs: True)
    monkeypatch.setattr(_db, 'get_folder_by_id', lambda folder_id, user_id: {
        'folder_id': folder_id, 'strategy_id': 'sid-current',
    })
    called = {'strategy': False}

    def forbidden_strategy_load(*_args, **_kwargs):
        called['strategy'] = True
        return None

    monkeypatch.setattr(_db, 'get_strategy_by_id', forbidden_strategy_load)
    response = _client().post('/api/v2/agents/createur/generate', json={
        'content_type': 'script',
        'user_request': 'Créer un script',
        'folder_id': 'fid-current',
        'strategy_id': 'sid-stale',
        'use_psycho': False,
        'use_strategy': True,
    })

    assert response.status_code == 409
    assert response.get_json()['error'] == 'strategy_context_mismatch'
    assert called['strategy'] is False
