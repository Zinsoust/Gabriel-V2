# ─── Gabriel — Tests suppression de compte ────────────────────────────────────
#
# Couvre /account/delete : confirmation par email, purge des fichiers locaux
# par utilisateur, et effacement de session.
# Lancer : cd /Users/easycash/Desktop/Gabriel && venv/bin/pytest tests/test_account_deletion.py -v

import os
import sys
import json

os.environ['AUTH_ENABLED']       = 'true'
os.environ['FLASK_SECRET_KEY']   = 'test-secret-deletion'
os.environ.setdefault('MISTRAL_API_KEY', 'test-key')
os.environ.setdefault('SUPABASE_URL', '')
os.environ.setdefault('SUPABASE_KEY', '')
os.environ['RATE_LIMIT_ENABLED'] = 'false'

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import app as _app
from core.memory import _memory_file

UID   = 'uid-deletion-tests'
EMAIL = 'deletion-tests@example.com'


def _client():
    c = _app.app.test_client()
    with c.session_transaction() as s:
        s['user_id']    = UID
        s['user_email'] = EMAIL
        s['user_name']  = 'Deletion Tester'
    return c


def _touch_user_files():
    os.makedirs(_app._PROFILES_DIR, exist_ok=True)
    os.makedirs(_app._CONTEXTS_DIR, exist_ok=True)
    os.makedirs(_app._CONVOS_DIR, exist_ok=True)
    paths = {
        'profile': os.path.join(_app._PROFILES_DIR, f"{UID}.json"),
        'context': os.path.join(_app._CONTEXTS_DIR, f"{UID}.json"),
        'convo':   os.path.join(_app._CONVOS_DIR, f"{UID}.json"),
        'memory':  _memory_file(UID),
    }
    for p in paths.values():
        with open(p, 'w', encoding='utf-8') as f:
            json.dump({'x': 1}, f)
    return paths


def test_delete_requires_matching_email():
    _touch_user_files()
    c = _client()
    r = c.post('/account/delete', json={'confirm_email': 'not-the-right-email@example.com'})
    assert r.status_code == 400
    assert r.get_json()['success'] is False


def test_delete_unauthenticated_returns_401():
    c = _app.app.test_client()
    r = c.post('/account/delete', json={'confirm_email': EMAIL})
    assert r.status_code == 401


def test_delete_purges_local_files_and_clears_session():
    paths = _touch_user_files()
    assert all(os.path.exists(p) for p in paths.values())

    c = _client()
    r = c.post('/account/delete', json={'confirm_email': EMAIL})
    assert r.status_code == 200
    assert r.get_json()['success'] is True

    assert not any(os.path.exists(p) for p in paths.values())

    # Session effacée → une route protégée redirige vers /login
    r2 = c.get('/profil')
    assert r2.status_code in (302, 301)
    assert 'login' in r2.headers.get('Location', '')


def test_delete_email_match_is_case_insensitive():
    _touch_user_files()
    c = _client()
    r = c.post('/account/delete', json={'confirm_email': EMAIL.upper()})
    assert r.status_code == 200
    assert r.get_json()['success'] is True
