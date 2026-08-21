"""Endpoint de préparation Cross Analyse : validation uniquement, aucun LLM."""

import os
import sys

os.environ['AUTH_ENABLED'] = 'true'
os.environ['FLASK_SECRET_KEY'] = 'test-secret-cross-analysis'
os.environ.setdefault('MISTRAL_API_KEY', 'test-key')
os.environ.setdefault('SUPABASE_URL', '')
os.environ.setdefault('SUPABASE_KEY', '')
os.environ['RATE_LIMIT_ENABLED'] = 'false'
os.environ['NLP_PRELOAD'] = 'false'

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import app as _app


def _client():
    client = _app.app.test_client()
    with client.session_transaction() as session:
        session['user_id'] = 'cross-analysis-user'
        session['user_email'] = 'cross@example.com'
        session['user_name'] = 'Cross Analysis'
    return client


def test_prepare_cross_analysis_returns_a_frontend_safe_contract():
    response = _client().post(
        '/api/v2/agents/psychologue/cross-analyses/prepare',
        json={
            'folder_id': 'workspace-cross-1',
            'sources': [
                {'platform': 'youtube', 'url': 'https://www.youtube.com/watch?v=dQw4w9WgXcQ'},
                {'platform': 'youtube', 'url': 'https://youtu.be/9bZkp7q19f0'},
            ],
        },
    )
    payload = response.get_json()

    assert response.status_code == 200
    assert payload['success'] is True
    assert payload['analysis_mode'] == 'cross'
    assert payload['state'] == 'prepared'
    assert payload['cross_analysis_id'].startswith('cross_')
    assert payload['folder_id'] == 'workspace-cross-1'
    assert [source['video_id'] for source in payload['sources']] == [
        'dQw4w9WgXcQ', '9bZkp7q19f0',
    ]


def test_prepare_cross_analysis_does_not_accept_a_single_source():
    response = _client().post(
        '/api/v2/agents/psychologue/cross-analyses/prepare',
        json={'sources': [{'url': 'https://www.youtube.com/watch?v=dQw4w9WgXcQ'}]},
    )

    assert response.status_code == 400
    assert 'entre 2 et 5 sources' in response.get_json()['error']


def test_prepare_cross_analysis_requires_an_authenticated_user():
    response = _app.app.test_client().post(
        '/api/v2/agents/psychologue/cross-analyses/prepare',
        json={'sources': [
            {'url': 'https://www.youtube.com/watch?v=dQw4w9WgXcQ'},
            {'url': 'https://youtu.be/9bZkp7q19f0'},
        ]},
    )

    assert response.status_code == 401
    assert response.get_json()['error_code'] == 'auth_required'
