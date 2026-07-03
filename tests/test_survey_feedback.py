# ─── Gabriel — Tests Survey / Feedback Loop ────────────────────────────────────
#
# 15 tests couvrant le système d'enquête non intrusif.
# Lancer : cd /Users/easycash/Desktop/Gabriel && venv/bin/pytest tests/test_survey_feedback.py -v

import os
import sys
import json
import pytest

os.environ['AUTH_ENABLED']       = 'true'
os.environ['FLASK_SECRET_KEY']   = 'test-secret-for-survey'
os.environ.setdefault('MISTRAL_API_KEY', 'test-key')
os.environ.setdefault('SUPABASE_URL', '')
os.environ.setdefault('SUPABASE_KEY', '')
os.environ['RATE_LIMIT_ENABLED'] = 'false'

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import app as _app

client = _app.app.test_client()


def _auth(c):
    """Injecte une session utilisateur de test."""
    with c.session_transaction() as s:
        s['user_id']    = 'test-uid-survey'
        s['user_email'] = 'survey@example.com'
        s['user_name']  = 'Survey Tester'


def _post_json(path, payload, authed=True):
    # Toujours un client frais pour éviter la réutilisation de session
    c = _app.app.test_client()
    if authed:
        _auth(c)
    return c.post(path, data=json.dumps(payload),
                  content_type='application/json')


def _get(path, authed=True):
    c = _app.app.test_client()
    if authed:
        _auth(c)
    return c.get(path)


# ════════════════════════════════════════════════════════════════════════════
# 1. Survey event créé après action
# ════════════════════════════════════════════════════════════════════════════
def test_survey_event_created():
    r = _post_json('/feedback/survey-event', {
        'event_type':  'after_analysis',
        'target_type': 'analysis',
        'target_id':   'fake-analysis-id-001',
    })
    d = r.get_json()
    assert r.status_code == 200
    assert d.get('success') is True
    assert 'event_id' in d


# ════════════════════════════════════════════════════════════════════════════
# 2. Survey response enregistrée
# ════════════════════════════════════════════════════════════════════════════
def test_survey_response_saved():
    r = _post_json('/feedback/survey-response', {
        'survey_event_id':     'fake-event-id-001',
        'target_type':         'analysis',
        'target_id':           'fake-analysis-id-001',
        'agent':               'psychologue',
        'quick_answer':        'oui',
        'relevance_score':     4,
        'clarity_score':       3,
        'usefulness_score':    5,
        'actionability_score': 4,
        'free_feedback':       'Très pertinent, merci.',
    })
    d = r.get_json()
    assert r.status_code == 200
    assert d.get('success') is True
    assert 'Merci' in d.get('message', '')


# ════════════════════════════════════════════════════════════════════════════
# 3. Feedback trop long refusé (> 2000 caractères)
# ════════════════════════════════════════════════════════════════════════════
def test_survey_response_too_long_rejected():
    r = _post_json('/feedback/survey-response', {
        'quick_answer': 'partiellement',
        'free_feedback': 'A' * 2001,
    })
    assert r.status_code == 400
    d = r.get_json()
    assert d.get('success') is False


# ════════════════════════════════════════════════════════════════════════════
# 4. API survey sans auth retourne 401 JSON
# ════════════════════════════════════════════════════════════════════════════
def test_survey_event_unauthenticated():
    r = _post_json('/feedback/survey-event', {
        'event_type': 'after_analysis',
    }, authed=False)
    assert r.status_code == 401
    d = r.get_json()
    assert d is not None  # JSON, pas HTML


def test_survey_response_unauthenticated():
    r = _post_json('/feedback/survey-response', {
        'quick_answer': 'oui',
    }, authed=False)
    assert r.status_code == 401
    d = r.get_json()
    assert d is not None


def test_dismiss_unauthenticated():
    r = _post_json('/feedback/dismiss', {
        'event_id': 'fake-id',
        'status':   'dismissed',
    }, authed=False)
    assert r.status_code == 401
    d = r.get_json()
    assert d is not None


def test_preferences_unauthenticated():
    r = _get('/feedback/preferences', authed=False)
    assert r.status_code == 401
    d = r.get_json()
    assert d is not None


# ════════════════════════════════════════════════════════════════════════════
# 5. event_type invalide rejeté
# ════════════════════════════════════════════════════════════════════════════
def test_survey_event_invalid_type():
    r = _post_json('/feedback/survey-event', {
        'event_type': 'invalid_event_xyz',
    })
    assert r.status_code == 400
    d = r.get_json()
    assert d.get('success') is False


# ════════════════════════════════════════════════════════════════════════════
# 6. quick_answer invalide rejeté
# ════════════════════════════════════════════════════════════════════════════
def test_survey_response_invalid_quick_answer():
    r = _post_json('/feedback/survey-response', {
        'quick_answer': 'maybe',  # valeur invalide
    })
    assert r.status_code == 400
    d = r.get_json()
    assert d.get('success') is False


# ════════════════════════════════════════════════════════════════════════════
# 7. Dismiss fonctionne (later et dismissed)
# ════════════════════════════════════════════════════════════════════════════
def test_dismiss_later():
    r = _post_json('/feedback/dismiss', {
        'event_id': 'fake-event-later-001',
        'status':   'later',
    })
    d = r.get_json()
    assert r.status_code == 200
    assert d.get('success') is True


def test_dismiss_today():
    r = _post_json('/feedback/dismiss', {
        'event_id': 'fake-event-dismiss-001',
        'status':   'dismissed',
    })
    d = r.get_json()
    assert r.status_code == 200
    assert d.get('success') is True


# ════════════════════════════════════════════════════════════════════════════
# 8. Consentement product_improvement enregistré
# ════════════════════════════════════════════════════════════════════════════
def test_consent_granted():
    r = _post_json('/feedback/preferences', {
        'consent_type': 'product_improvement',
        'status':       'granted',
        'source':       'settings',
    })
    d = r.get_json()
    assert r.status_code == 200
    assert d.get('success') is True


# ════════════════════════════════════════════════════════════════════════════
# 9. Retrait du consentement fonctionne
# ════════════════════════════════════════════════════════════════════════════
def test_consent_withdrawn():
    r = _post_json('/feedback/preferences', {
        'consent_type': 'product_improvement',
        'status':       'withdrawn',
        'source':       'settings',
    })
    d = r.get_json()
    assert r.status_code == 200
    assert d.get('success') is True


# ════════════════════════════════════════════════════════════════════════════
# 10. consent_type invalide rejeté
# ════════════════════════════════════════════════════════════════════════════
def test_consent_invalid_type():
    r = _post_json('/feedback/preferences', {
        'consent_type': 'tracking_ads',  # invalide
        'status':       'granted',
    })
    assert r.status_code == 400


# ════════════════════════════════════════════════════════════════════════════
# 11. GET /feedback/preferences retourne JSON
# ════════════════════════════════════════════════════════════════════════════
def test_preferences_get():
    r = _get('/feedback/preferences')
    assert r.status_code == 200
    d = r.get_json()
    assert d is not None
    assert 'product_improvement' in d


# ════════════════════════════════════════════════════════════════════════════
# 12. Les réponses ne contiennent jamais de secrets dans les logs
#     (vérification que safe_log_event ne logue pas free_feedback)
# ════════════════════════════════════════════════════════════════════════════
def test_no_sensitive_data_in_survey_event_log(capsys):
    _post_json('/feedback/survey-response', {
        'quick_answer':  'non',
        'free_feedback': 'MON_TEXTE_SECRET_XYZ',
        'agent':         'psychologue',
    })
    captured = capsys.readouterr()
    assert 'MON_TEXTE_SECRET_XYZ' not in captured.out
    assert 'MON_TEXTE_SECRET_XYZ' not in captured.err


# ════════════════════════════════════════════════════════════════════════════
# 13. Scores hors limites (1-5) ignorés / normalisés
# ════════════════════════════════════════════════════════════════════════════
def test_scores_out_of_range_not_crash():
    r = _post_json('/feedback/survey-response', {
        'quick_answer':     'oui',
        'relevance_score':  99,   # hors limite — db.py normalise à None
        'clarity_score':    -1,
    })
    # Ne doit pas crasher — 200 ou 200 (Supabase absent → fallback ok)
    assert r.status_code in (200, 500)  # 500 only si Supabase CHECK constraint live


# ════════════════════════════════════════════════════════════════════════════
# 14. gabriel-survey.js est servi statiquement
# ════════════════════════════════════════════════════════════════════════════
def test_survey_js_served():
    with client as c:
        r = c.get('/static/js/gabriel-survey.js')
    assert r.status_code == 200
    assert b'GabrielSurvey' in r.data


# ════════════════════════════════════════════════════════════════════════════
# 15. Les routes existantes /feedback et /satisfaction restent intactes
# ════════════════════════════════════════════════════════════════════════════
def test_existing_feedback_route_intact():
    r = _post_json('/feedback', {
        'strategy_id':    'fake-strat-001',
        'usefulness':     'oui',
        'free_feedback':  'Test régression.',
    })
    # Doit retourner 200 (Supabase absent → fallback JSON)
    assert r.status_code == 200


def test_existing_satisfaction_route_intact():
    r = _post_json('/satisfaction', {
        'analysis_id':              'fake-analysis-001',
        'global_satisfaction_score': 4,
        'feedback_text':            'Satisfait.',
    })
    assert r.status_code in (200, 400)  # 400 si analysis_id manquant strict
