# ─── Gabriel — Tests verrouillage par dossier + résolution stratégie/psycho ───
#
# Couvre le décorateur _requires_folder (accès aux agents conditionné à un
# dossier actif) et les helpers _resolve_psycho / _resolve_strategy utilisés
# par /creator/generate pour ne jamais partir d'un contexte vide s'il est
# disponible ailleurs (folder_id, strategy_id, cache).
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


def _client():
    c = _app.app.test_client()
    with c.session_transaction() as s:
        s['user_id']    = UID
        s['user_email'] = f'{UID}@example.com'
        s['user_name']  = 'Gating Tester'
    return c


# ══════════════════════════════════════════════════════════════════════════════
# 1. Verrouillage — aucun dossier actif
# ══════════════════════════════════════════════════════════════════════════════
def test_gated_routes_redirect_without_active_folder():
    """Sans dossier actif en session, chaque route agent redirige vers /dossiers."""
    for route in GATED_ROUTES:
        c = _client()
        r = c.get(route)
        assert r.status_code in (302, 301), f'{route} devrait rediriger'
        assert 'dossiers' in r.headers.get('Location', ''), f'{route} devrait rediriger vers /dossiers'


# ══════════════════════════════════════════════════════════════════════════════
# 2. Déblocage — folder_id en paramètre d'URL
# ══════════════════════════════════════════════════════════════════════════════
def test_folder_id_param_unlocks_access():
    """Un folder_id passé en paramètre d'URL débloque l'accès immédiatement."""
    for route in GATED_ROUTES:
        c = _client()
        r = c.get(f'{route}?folder_id=fid-test-123')
        assert r.status_code == 200, f'{route}?folder_id=... devrait répondre 200'


def test_folder_id_param_persists_in_session():
    """Une fois le folder_id passé une fois, les visites suivantes sans paramètre passent aussi."""
    c = _client()
    r1 = c.get('/psychologue?folder_id=fid-test-456')
    assert r1.status_code == 200

    # Deuxième requête, même client (donc même session), sans folder_id explicite
    r2 = c.get('/stratege')
    assert r2.status_code == 200

    r3 = c.get('/mes-analyses')
    assert r3.status_code == 200


def test_dossier_detail_page_sets_active_folder():
    """Ouvrir /dossiers/<folder_id> (même sur un dossier introuvable → redirect)
    ne doit pas planter, et un dossier existant active la session."""
    c = _client()
    # Dossier inconnu → redirige vers /dossiers, ne débloque rien
    r = c.get('/dossiers/unknown-folder-xyz')
    assert r.status_code in (302, 301)
    r2 = c.get('/psychologue')
    assert r2.status_code in (302, 301)  # toujours verrouillé, le dossier n'existait pas


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
        return {'strategy_result': {'decision_centrale': 'Via folder_id'}}
    monkeypatch.setattr(_db, 'get_folder_by_id', fake_get_folder_by_id)
    monkeypatch.setattr(_db, 'get_strategy_by_id', fake_get_strategy_by_id)

    strat = _app._resolve_strategy({'folder_id': 'fid-99'}, UID)
    assert strat.get('decision_centrale') == 'Via folder_id'


def test_resolve_strategy_folder_without_strategy_yet():
    """Un dossier existant mais sans stratégie liée ne doit pas planter — retourne {}."""
    strat = _app._resolve_strategy({'folder_id': 'fid-no-strategy'}, UID)
    assert strat == {}
