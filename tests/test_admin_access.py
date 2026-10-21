"""Negative and positive authorization tests; no external services."""

import os

os.environ['AUTH_ENABLED'] = 'true'
os.environ['FLASK_SECRET_KEY'] = 'test-secret-admin-access'
os.environ['RATE_LIMIT_ENABLED'] = 'false'
os.environ.setdefault('SUPABASE_URL', '')
os.environ.setdefault('SUPABASE_KEY', '')

import app as _app
import api.db as _db
from core.admin_access import configured_admin_user_ids, is_admin_user


ADMIN_ID = '11111111-1111-4111-8111-111111111111'
STANDARD_ID = '22222222-2222-4222-8222-222222222222'
OLD_EMAIL = 'outilsagencechretienne@gmail.com'
PUBLIC_EMAIL = 'gabrielaigithub@gmail.com'


def _client(user_id=None, email='user@example.com'):
    client = _app.app.test_client()
    if user_id:
        with client.session_transaction() as session:
            session['user_id'] = user_id
            session['user_email'] = email
            session['user_name'] = 'Test'
    return client


def test_admin_configuration_is_fail_closed(monkeypatch):
    monkeypatch.delenv('ADMIN_USER_IDS', raising=False)
    assert configured_admin_user_ids() == frozenset()
    assert not is_admin_user({'user_id': ADMIN_ID, 'email': OLD_EMAIL})

    monkeypatch.setenv('ADMIN_USER_IDS', f'{ADMIN_ID},not-an-internal-uuid')
    assert configured_admin_user_ids() == frozenset()
    assert not is_admin_user({'user_id': ADMIN_ID})


def test_old_and_public_email_never_grant_admin(monkeypatch):
    monkeypatch.delenv('ADMIN_USER_IDS', raising=False)
    for email in (OLD_EMAIL, PUBLIC_EMAIL):
        user = {'user_id': STANDARD_ID, 'email': email}
        assert not is_admin_user(user)
        assert _client(STANDARD_ID, email).get('/studio/stratege').status_code == 403


def test_spoofed_configured_admin_email_does_not_grant_admin(monkeypatch):
    monkeypatch.setenv('ADMIN_USER_IDS', ADMIN_ID)
    spoofed = _client(STANDARD_ID, 'admin@example.com')
    assert spoofed.get('/studio/stratege').status_code == 403
    assert spoofed.post('/rag/reload', json={'agent': 'stratege'}).status_code == 403


def test_standard_and_unauthenticated_accounts_are_refused(monkeypatch):
    monkeypatch.setenv('ADMIN_USER_IDS', ADMIN_ID)
    assert _client(STANDARD_ID).get('/studio/stratege').status_code == 403
    assert _client().get('/studio/stratege').status_code in (301, 302)
    assert _client().post('/rag/reload', json={'agent': 'stratege'}).status_code == 401


def test_configured_admin_id_can_use_studio_publish_and_rag(monkeypatch):
    monkeypatch.setenv('ADMIN_USER_IDS', ADMIN_ID)
    monkeypatch.setattr(_db, 'get_ux_settings', lambda page: None)
    monkeypatch.setattr(
        _db, 'publish_ux_settings',
        lambda page, settings, author: {'version': 1, 'published': settings},
    )
    import core.rag as rag
    reloads = []
    monkeypatch.setattr(rag, 'reload', lambda agent: reloads.append(agent))

    admin = _client(ADMIN_ID, OLD_EMAIL)
    assert admin.get('/studio/stratege').status_code == 200
    assert admin.get('/api/studio/stratege/settings').status_code == 200
    assert admin.post('/api/studio/stratege/publish', json={'settings': {}}).status_code == 200
    assert admin.post('/rag/reload', json={'agent': 'stratege'}).status_code == 200
    assert reloads == ['stratege']


def test_email_cannot_bypass_usage_or_credit_limits(monkeypatch):
    monkeypatch.delenv('ADMIN_USER_IDS', raising=False)
    monkeypatch.setenv('AUTH_ENABLED', 'true')
    monkeypatch.setattr(_db, 'count_user_analyses', lambda user_id: _db.FREE_ANALYSES_LIMIT)
    monkeypatch.setattr(_db, 'get_user_plan', lambda user_id: 'free')
    monkeypatch.setattr(_db, 'get_user_credits', lambda user_id: 0)

    usage = _db.check_usage_limit(STANDARD_ID, email=OLD_EMAIL)
    assert usage['allowed'] is False
    assert _db.has_enough_credits(STANDARD_ID, 1, email=OLD_EMAIL) is False


def test_configured_admin_id_bypasses_quota_but_not_broken_credit_store(monkeypatch):
    monkeypatch.setenv('ADMIN_USER_IDS', ADMIN_ID)
    monkeypatch.setenv('AUTH_ENABLED', 'true')
    monkeypatch.setattr(_db, 'count_user_analyses', lambda user_id: _db.FREE_ANALYSES_LIMIT)
    assert _db.check_usage_limit(ADMIN_ID, email='anything@example.com')['plan'] == 'admin'

    def unavailable(_user_id):
        raise _db.CreditStoreUnavailable('offline')

    monkeypatch.setattr(_db, 'get_user_credits', unavailable)
    try:
        _db.has_enough_credits(ADMIN_ID, 1)
    except _db.CreditStoreUnavailable:
        pass
    else:
        raise AssertionError('an admin must not bypass an unavailable credit store')
