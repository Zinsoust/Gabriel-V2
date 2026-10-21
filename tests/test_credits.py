# ─── Gabriel — Tests système de crédits ───────────────────────────────────────
#
# Couvre le solde de crédits (api/db.py, mode JSON/mémoire sans Supabase) et
# le blocage 402 sur /analyze, /strategize, /creator/generate quand le solde
# est insuffisant.
# Lancer : cd /Users/easycash/Desktop/Gabriel && venv/bin/pytest tests/test_credits.py -v

import os
import sys
import json
import uuid
import pytest

os.environ['AUTH_ENABLED']       = 'true'
os.environ['FLASK_SECRET_KEY']   = 'test-secret-credits'
os.environ.setdefault('MISTRAL_API_KEY', 'test-key')
os.environ.setdefault('SUPABASE_URL', '')
os.environ.setdefault('SUPABASE_KEY', '')
os.environ['RATE_LIMIT_ENABLED'] = 'false'

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import api.db as _db
import app as _app


def _client(uid):
    c = _app.app.test_client()
    with c.session_transaction() as s:
        s['user_id']    = uid
        s['user_email'] = f'{uid}@example.com'
        s['user_name']  = 'Credits Tester'
    return c


# ══════════════════════════════════════════════════════════════════════════════
# 1. Solde initial — les 300 crédits viennent d'un compte persisté
# ══════════════════════════════════════════════════════════════════════════════
def test_get_user_credits_initial_balance_is_300(monkeypatch, tmp_path):
    uid = f'uid-credits-{uuid.uuid4().hex[:8]}'
    (tmp_path / 'users.json').write_text(
        json.dumps({uid: {'user_id': uid, 'credits': _db.DEFAULT_FREE_CREDITS}}),
        encoding='utf-8',
    )
    monkeypatch.setattr(_db, '_supabase', None)
    monkeypatch.setattr(_db, '_DATA_DIR', str(tmp_path))
    assert _db.get_user_credits(uid) == _db.DEFAULT_FREE_CREDITS == 300


def test_get_user_credits_unknown_account_is_not_given_free_credits(monkeypatch, tmp_path):
    (tmp_path / 'users.json').write_text('{}', encoding='utf-8')
    monkeypatch.setattr(_db, '_supabase', None)
    monkeypatch.setattr(_db, '_DATA_DIR', str(tmp_path))
    with pytest.raises(_db.CreditAccountNotFound):
        _db.get_user_credits('unknown-user')


def test_get_user_credits_no_user_id():
    assert _db.get_user_credits(None) == 0
    assert _db.get_user_credits('') == 0


def test_agent_credit_costs_match_current_pricing():
    assert _db.CREDIT_COSTS == {
        'psychologue': 80,
        'stratege': 50,
        'createur': 20,
    }


# ══════════════════════════════════════════════════════════════════════════════
# 2. Déduction — persistée en JSON, jamais sous zéro
# ══════════════════════════════════════════════════════════════════════════════
def test_deduct_credits_persists_in_json(monkeypatch, tmp_path):
    users_file = tmp_path / 'users.json'
    uid = 'uid-deduct-1'
    users_file.write_text(json.dumps({uid: {'user_id': uid, 'credits': 300}}), encoding='utf-8')
    monkeypatch.setattr(_db, '_DATA_DIR', str(tmp_path))

    balance = _db.deduct_credits(uid, 100, reason='psychologue')
    assert balance == 200
    assert _db.get_user_credits(uid) == 200

    on_disk = json.loads(users_file.read_text(encoding='utf-8'))
    assert on_disk[uid]['credits'] == 200


def test_deduct_credits_never_goes_negative(monkeypatch, tmp_path):
    users_file = tmp_path / 'users.json'
    uid = 'uid-deduct-2'
    users_file.write_text(json.dumps({uid: {'user_id': uid, 'credits': 30}}), encoding='utf-8')
    monkeypatch.setattr(_db, '_DATA_DIR', str(tmp_path))

    balance = _db.deduct_credits(uid, 100, reason='psychologue')
    assert balance == 0
    assert _db.get_user_credits(uid) == 0


def test_deduct_credits_noop_without_user_id(monkeypatch, tmp_path):
    uid = 'some-uid'
    (tmp_path / 'users.json').write_text(
        json.dumps({uid: {'user_id': uid, 'credits': 300}}), encoding='utf-8')
    monkeypatch.setattr(_db, '_supabase', None)
    monkeypatch.setattr(_db, '_DATA_DIR', str(tmp_path))
    assert _db.deduct_credits(None, 100) == 0
    assert _db.deduct_credits(uid, 0) == _db.get_user_credits(uid)


# ══════════════════════════════════════════════════════════════════════════════
# 3. has_enough_credits — bypass dev/admin, gating normal sinon
# ══════════════════════════════════════════════════════════════════════════════
def test_has_enough_credits_bypass_dev_mode(monkeypatch):
    monkeypatch.setenv('AUTH_ENABLED', 'false')
    monkeypatch.setattr(_db, 'get_user_credits', lambda uid: 0)
    assert _db.has_enough_credits('any-uid', 999999) is True
    monkeypatch.setenv('AUTH_ENABLED', 'true')  # restaure pour les autres tests du module


def test_has_enough_credits_bypass_admin_user_id(monkeypatch):
    admin_id = '11111111-1111-4111-8111-111111111111'
    monkeypatch.setenv('ADMIN_USER_IDS', admin_id)
    monkeypatch.setattr(_db, 'get_user_credits', lambda uid: 0)
    assert _db.has_enough_credits(admin_id, 999999, email='spoofed@example.com') is True


def test_has_enough_credits_gates_normal_user(monkeypatch, tmp_path):
    users_file = tmp_path / 'users.json'
    uid = 'uid-gate-1'
    users_file.write_text(json.dumps({uid: {'user_id': uid, 'credits': 50}}), encoding='utf-8')
    monkeypatch.setattr(_db, '_DATA_DIR', str(tmp_path))
    monkeypatch.delenv('ADMIN_USER_IDS', raising=False)

    assert _db.has_enough_credits(uid, 50) is True
    assert _db.has_enough_credits(uid, 51) is False


# ══════════════════════════════════════════════════════════════════════════════
# 4. Routes — 402 credits_insufficient quand le solde est insuffisant
# ══════════════════════════════════════════════════════════════════════════════
def test_analyze_blocked_when_credits_insufficient(monkeypatch):
    monkeypatch.setattr(_db, 'check_usage_limit', lambda uid, email=None: {'allowed': True})
    monkeypatch.setattr(_db, 'has_enough_credits', lambda uid, cost, email=None: False)
    monkeypatch.setattr(_db, 'get_user_credits', lambda uid: 0)

    c = _client('uid-block-analyze')
    r = c.post('/analyze',
               data=json.dumps({'source': 'text',
                                'content': 'Un commentaire\nDeux commentaires\nTrois commentaires'}),
               content_type='application/json')
    d = r.get_json()
    assert r.status_code == 402
    assert d['error'] == 'credits_insufficient'
    assert d['upgrade_required'] is True
    assert d['cost'] == _db.CREDIT_COSTS['psychologue']


def test_strategize_blocked_when_credits_insufficient(monkeypatch):
    monkeypatch.setattr(_db, 'has_enough_credits', lambda uid, cost, email=None: False)
    monkeypatch.setattr(_db, 'get_user_credits', lambda uid: 0)

    c = _client('uid-block-strategize')
    r = c.post('/strategize',
               data=json.dumps({'context': {'activite': 'Test', 'offre': 'Test',
                                             'cible': 'Test', 'objectif': 'Test'}}),
               content_type='application/json')
    d = r.get_json()
    assert r.status_code == 402
    assert d['error'] == 'credits_insufficient'
    assert d['cost'] == _db.CREDIT_COSTS['stratege']


def test_creator_generate_blocked_when_credits_insufficient(monkeypatch):
    monkeypatch.setattr(_db, 'has_enough_credits', lambda uid, cost, email=None: False)
    monkeypatch.setattr(_db, 'get_user_credits', lambda uid: 0)

    c = _client('uid-block-creator')
    r = c.post('/creator/generate',
               data=json.dumps({'content_type': 'linkedin_post', 'user_request': 'Un post'}),
               content_type='application/json')
    d = r.get_json()
    assert r.status_code == 402
    assert d['error'] == 'credits_insufficient'
    assert d['cost'] == _db.CREDIT_COSTS['createur']


def test_credits_route_returns_balance(monkeypatch):
    uid = 'uid-route-credits'
    monkeypatch.setattr(_db, 'get_user_credits', lambda user_id: 300 if user_id == uid else 0)
    c = _client(uid)
    r = c.get('/credits')
    assert r.status_code == 200
    assert r.get_json()['credits'] == _db.DEFAULT_FREE_CREDITS
