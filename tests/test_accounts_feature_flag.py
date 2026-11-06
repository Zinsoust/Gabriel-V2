import os

os.environ.setdefault('FLASK_SECRET_KEY', 'test-accounts-feature-flag-secret')
os.environ.setdefault('AUTH_ENABLED', 'true')
os.environ.setdefault('NLP_PRELOAD', 'false')
os.environ.setdefault('RAG_PRELOAD', 'false')

import api.auth as auth
from app import app, production_safety_problems


SECRET_OK = 'x' * 40


def test_accounts_default_open_locally_and_closed_on_render(monkeypatch):
    monkeypatch.delenv('GABRIEL_ACCOUNTS_ENABLED', raising=False)
    monkeypatch.delenv('RENDER', raising=False)
    monkeypatch.delenv('RENDER_EXTERNAL_URL', raising=False)
    monkeypatch.setenv('GABRIEL_ENV', 'development')
    assert auth.accounts_enabled() is True

    monkeypatch.setenv('RENDER', 'true')
    assert auth.accounts_enabled() is False


def test_explicit_account_flag_controls_the_feature(monkeypatch):
    monkeypatch.setenv('RENDER', 'true')
    monkeypatch.setenv('GABRIEL_ACCOUNTS_ENABLED', 'true')
    assert auth.accounts_enabled() is True
    monkeypatch.setenv('GABRIEL_ACCOUNTS_ENABLED', 'false')
    assert auth.accounts_enabled() is False


def test_public_site_stays_up_while_private_access_is_closed(monkeypatch):
    monkeypatch.setenv('AUTH_ENABLED', 'true')
    monkeypatch.setenv('RENDER', 'true')
    monkeypatch.setenv('GABRIEL_ACCOUNTS_ENABLED', 'false')
    client = app.test_client()

    assert client.get('/').status_code == 200
    login = client.get('/login')
    assert login.status_code == 200
    assert b'name="password"' not in login.data

    protected = client.get('/orchestrateur')
    assert protected.status_code == 302
    assert 'accounts_disabled' in protected.headers['Location']

    api_response = client.post('/api/v2/agents/psychologue/analyze', json={
        'source': 'text', 'content': 'commentaire synthetique',
    })
    assert api_response.status_code == 503
    assert api_response.get_json()['error_code'] == 'accounts_disabled'


def test_account_actions_are_fail_closed(monkeypatch):
    monkeypatch.setenv('RENDER', 'true')
    monkeypatch.setenv('GABRIEL_ACCOUNTS_ENABLED', 'false')
    client = app.test_client()

    assert client.post('/login/email', data={}).status_code == 503
    assert client.post('/register', data={}).status_code == 503
    assert client.get('/auth/google').status_code == 302
    assert 'accounts_disabled' in client.get('/auth/google').headers['Location']


def test_failed_login_keeps_the_form_when_accounts_are_enabled(monkeypatch):
    monkeypatch.delenv('RENDER', raising=False)
    monkeypatch.delenv('RENDER_EXTERNAL_URL', raising=False)
    monkeypatch.setenv('GABRIEL_ENV', 'development')
    monkeypatch.setenv('GABRIEL_ACCOUNTS_ENABLED', 'true')
    client = app.test_client()

    response = client.post('/login/email', data={
        'email': 'personne@example.test',
        'password': 'mot-de-passe-invalide',
    })
    assert response.status_code == 200
    assert b'name="password"' in response.data


def test_deployed_accounts_require_supabase_configuration():
    base = {
        'RENDER': 'true',
        'AUTH_ENABLED': 'true',
        'FLASK_SECRET_KEY': SECRET_OK,
        'GABRIEL_ACCOUNTS_ENABLED': 'true',
    }
    problems = production_safety_problems(base)
    assert any('SUPABASE_URL' in problem for problem in problems)
    assert any('SUPABASE_KEY' in problem for problem in problems)

    configured = {
        **base,
        'SUPABASE_URL': 'https://example.supabase.co',
        'SUPABASE_KEY': 'server-key-placeholder',
    }
    assert production_safety_problems(configured) == []
