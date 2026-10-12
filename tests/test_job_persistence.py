# ─── Gabriel — Tests persistance des jobs d'analyse ───────────────────────────
#
# Couvre le cycle de vie des jobs (mémoire + Supabase) et la récupération
# après redémarrage serveur (simulation : job absent de la mémoire).
# Lancer : cd /Users/easycash/Desktop/Gabriel && venv/bin/pytest tests/test_job_persistence.py -v

import os
import sys
import json
import pytest

os.environ['AUTH_ENABLED']       = 'true'
os.environ['FLASK_SECRET_KEY']   = 'test-secret-for-jobs'
os.environ.setdefault('MISTRAL_API_KEY', 'test-key')
os.environ.setdefault('SUPABASE_URL', '')
os.environ.setdefault('SUPABASE_KEY', '')
os.environ['RATE_LIMIT_ENABLED'] = 'false'

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import app as _app
import api.db as _db

UID = 'test-uid-jobs'


def _client():
    c = _app.app.test_client()
    with c.session_transaction() as s:
        s['user_id']    = UID
        s['user_email'] = 'jobs@example.com'
        s['user_name']  = 'Jobs Tester'
    return c


@pytest.fixture
def funded_credit_store(monkeypatch, tmp_path):
    """Provide an isolated, funded local credit account for paid job tests."""
    users_file = tmp_path / 'users.json'
    users_file.write_text(
        json.dumps({
            UID: {
                'user_id': UID,
                'email': 'jobs@example.com',
                'credits': _db.DEFAULT_FREE_CREDITS,
            },
        }),
        encoding='utf-8',
    )
    monkeypatch.setattr(_db, '_supabase', None)
    monkeypatch.setattr(_db, '_DATA_DIR', str(tmp_path))
    return users_file


def _assert_psychologist_debit(users_file):
    users = json.loads(users_file.read_text(encoding='utf-8'))
    assert users[UID]['credits'] == (
        _db.DEFAULT_FREE_CREDITS - _db.CREDIT_COSTS['psychologue']
    )


# ════════════════════════════════════════════════════════════════════════════
# 1. Job en mémoire — status running (avec step/progress)
# ════════════════════════════════════════════════════════════════════════════
def test_status_running_in_memory():
    _app._jobs['job-mem-run'] = {'status': 'running', 'user_id': UID,
                                 'step': 'llm_principal', 'progress': 40}
    r = _client().get('/status/job-mem-run')
    d = r.get_json()
    assert r.status_code == 200
    assert d['status'] == 'running'
    assert d['progress'] == 40
    assert d['step'] == 'llm_principal'
    _app._jobs.pop('job-mem-run', None)


# ════════════════════════════════════════════════════════════════════════════
# 2. Job en mémoire — status done (résultat consommé une seule fois)
# ════════════════════════════════════════════════════════════════════════════
def test_status_done_in_memory():
    _app._jobs['job-mem-done'] = {'status': 'done', 'user_id': UID,
                                  'result': {'analysis_id': 'a1', 'kpis': {}}}
    r = _client().get('/status/job-mem-done')
    d = r.get_json()
    assert r.status_code == 200
    assert d['status'] == 'done'
    assert d['data']['analysis_id'] == 'a1'
    assert _app._jobs['job-mem-done']['status'] == 'consumed'
    _app._jobs.pop('job-mem-done', None)


# ════════════════════════════════════════════════════════════════════════════
# 3. Job en mémoire — status error
# ════════════════════════════════════════════════════════════════════════════
def test_status_error_in_memory():
    _app._jobs['job-mem-err'] = {'status': 'error', 'user_id': UID,
                                 'error': 'Boom contrôlé'}
    r = _client().get('/status/job-mem-err')
    d = r.get_json()
    assert r.status_code == 200
    assert d['status'] == 'error'
    assert 'Boom' in d['error']
    _app._jobs.pop('job-mem-err', None)


# ════════════════════════════════════════════════════════════════════════════
# 4. Isolation : un user ne peut pas lire le job d'un autre
# ════════════════════════════════════════════════════════════════════════════
def test_status_other_user_job_hidden():
    _app._jobs['job-other'] = {'status': 'running', 'user_id': 'someone-else'}
    r = _client().get('/status/job-other')
    assert r.status_code == 404
    _app._jobs.pop('job-other', None)


# ════════════════════════════════════════════════════════════════════════════
# 5. Simulation restart : job absent mémoire + absent DB → 404 propre
# ════════════════════════════════════════════════════════════════════════════
def test_status_unknown_job_404():
    r = _client().get('/status/job-doesnt-exist')
    d = r.get_json()
    assert r.status_code == 404
    assert d['status'] == 'not_found'


# ════════════════════════════════════════════════════════════════════════════
# 6. Simulation restart : job perdu en mémoire mais présent en DB (running)
#    → doit retourner 'interrupted', pas 404
# ════════════════════════════════════════════════════════════════════════════
def test_status_recovered_from_db_interrupted(monkeypatch):
    def fake_get_job(job_id, user_id=None):
        if job_id == 'job-db-lost' and user_id == UID:
            return {'job_id': job_id, 'user_id': user_id,
                    'status': 'running', 'progress': 40, 'step': 'llm_principal'}
        return None

    monkeypatch.setattr(_db, 'get_job', fake_get_job)
    monkeypatch.setattr(_db, 'update_job', lambda *a, **k: True)

    r = _client().get('/status/job-db-lost')
    d = r.get_json()
    assert r.status_code == 200
    assert d['status'] == 'interrupted'
    assert 'redémarrage' in d['error']


# ════════════════════════════════════════════════════════════════════════════
# 7. Simulation restart : job completed en DB → résultat récupéré
# ════════════════════════════════════════════════════════════════════════════
def test_status_recovered_from_db_completed(monkeypatch):
    def fake_get_job(job_id, user_id=None):
        if job_id == 'job-db-done' and user_id == UID:
            return {'job_id': job_id, 'user_id': user_id, 'status': 'completed',
                    'result_data': {'analysis_id': 'a2', 'kpis': {}}}
        return None

    monkeypatch.setattr(_db, 'get_job', fake_get_job)

    r = _client().get('/status/job-db-done')
    d = r.get_json()
    assert r.status_code == 200
    assert d['status'] == 'done'
    assert d['data']['analysis_id'] == 'a2'


# ════════════════════════════════════════════════════════════════════════════
# 8. Simulation restart : job failed en DB → erreur propre
# ════════════════════════════════════════════════════════════════════════════
def test_status_recovered_from_db_failed(monkeypatch):
    def fake_get_job(job_id, user_id=None):
        if job_id == 'job-db-fail' and user_id == UID:
            return {'job_id': job_id, 'user_id': user_id, 'status': 'failed',
                    'error_message': 'Erreur d analyse'}
        return None

    monkeypatch.setattr(_db, 'get_job', fake_get_job)

    r = _client().get('/status/job-db-fail')
    d = r.get_json()
    assert r.status_code == 200
    assert d['status'] == 'error'
    assert 'Erreur' in d['error']


# ════════════════════════════════════════════════════════════════════════════
# 9. db.create_job / update_job / get_job sans Supabase → dégradation propre
# ════════════════════════════════════════════════════════════════════════════
def test_db_job_helpers_without_supabase():
    assert _db.create_job('j1', UID) is False
    assert _db.update_job('j1', user_id=UID, status='running') is False
    assert _db.get_job('j1', user_id=UID) is None


# ════════════════════════════════════════════════════════════════════════════
# 10. /analyze crée un job et retourne job_id (100 commentaires, LLM mocké)
# ════════════════════════════════════════════════════════════════════════════
def test_analyze_creates_job_100_comments(monkeypatch, funded_credit_store):
    # 100 commentaires — la promesse produit minimum
    comments = '\n'.join(f'Commentaire numéro {i} vraiment intéressant' for i in range(100))

    def fake_run_psycho(self, comments, video_context='', title='', progress_cb=None, partial_cb=None):
        if progress_cb:
            progress_cb('nlp', 5)
            progress_cb('llm_principal', 40)
        return {'kpis': {}, 'meta': {'total_commentaires': len(comments)}}

    monkeypatch.setattr(type(_app.gabriel), 'run_psycho', fake_run_psycho)
    monkeypatch.setattr(_db, 'check_usage_limit',
                        lambda uid, email=None: {'allowed': True})
    monkeypatch.setattr(_db, 'save_analysis', lambda entry, uid, folder_id=None: None)

    c = _client()
    r = c.post('/analyze', data=json.dumps({'source': 'text', 'content': comments}),
               content_type='application/json')
    d = r.get_json()
    assert r.status_code == 200
    assert d.get('job_id')
    assert d.get('status') == 'running'

    # Attendre la fin du thread d'analyse (mock = quasi instantané)
    import time
    for _ in range(50):
        job = _app._jobs.get(d['job_id'])
        if job and job['status'] in ('done', 'error'):
            break
        time.sleep(0.1)
    assert _app._jobs[d['job_id']]['status'] == 'done'
    result = _app._jobs[d['job_id']]['result']
    assert result['meta']['total_commentaires'] == 100
    _assert_psychologist_debit(funded_credit_store)
    _app._jobs.pop(d['job_id'], None)


# ════════════════════════════════════════════════════════════════════════════
# 11. progress_cb met à jour step/progress dans le job mémoire
# ════════════════════════════════════════════════════════════════════════════
def test_progress_cb_updates_job(monkeypatch, funded_credit_store):
    captured = {}

    def fake_run_psycho(self, comments, video_context='', title='', progress_cb=None, partial_cb=None):
        if progress_cb:
            progress_cb('rag', 30)
        # Capturer l'état du job au moment du callback
        for jid, j in _app._jobs.items():
            if j.get('step') == 'rag':
                captured['progress'] = j.get('progress')
        return {'kpis': {}, 'meta': {'total_commentaires': 3}}

    monkeypatch.setattr(type(_app.gabriel), 'run_psycho', fake_run_psycho)
    monkeypatch.setattr(_db, 'check_usage_limit',
                        lambda uid, email=None: {'allowed': True})
    monkeypatch.setattr(_db, 'save_analysis', lambda entry, uid, folder_id=None: None)

    c = _client()
    r = c.post('/analyze',
               data=json.dumps({'source': 'text',
                                'content': 'Un commentaire\nDeux commentaires\nTrois commentaires'}),
               content_type='application/json')
    d = r.get_json()
    assert r.status_code == 200

    import time
    for _ in range(50):
        job = _app._jobs.get(d['job_id'])
        if job and job['status'] in ('done', 'error'):
            break
        time.sleep(0.1)
    assert _app._jobs[d['job_id']]['status'] == 'done'
    assert captured.get('progress') == 30
    _assert_psychologist_debit(funded_credit_store)
    _app._jobs.pop(d['job_id'], None)


# ════════════════════════════════════════════════════════════════════════════
# 12. /status expose 'partial' pendant qu'un job est encore en cours
# ════════════════════════════════════════════════════════════════════════════
def test_status_running_exposes_partial():
    _app._jobs['job-mem-partial'] = {
        'status': 'running', 'user_id': UID,
        'step': 'llm_paralleles', 'progress': 65,
        'partial': {'dashboard': {'dashboard': {'dominant_emotion': 'joie'}, 'meta': {}}},
    }
    r = _client().get('/status/job-mem-partial')
    d = r.get_json()
    assert r.status_code == 200
    assert d['status'] == 'running'
    assert d['partial']['dashboard']['dashboard']['dominant_emotion'] == 'joie'
    assert 'personas' not in d['partial']
    _app._jobs.pop('job-mem-partial', None)


# ════════════════════════════════════════════════════════════════════════════
# 13. partial_cb du pipeline alimente bien _jobs[id]['partial'] via /analyze
# ════════════════════════════════════════════════════════════════════════════
def test_partial_cb_updates_job(monkeypatch, funded_credit_store):
    captured = {}

    def fake_run_psycho(self, comments, video_context='', title='', progress_cb=None, partial_cb=None):
        if partial_cb:
            partial_cb('dashboard', {'dashboard': {'dominant_emotion': 'joie'}, 'meta': {}})
            for jid, j in _app._jobs.items():
                if j.get('partial', {}).get('dashboard'):
                    captured['seen_before_done'] = True
        return {'kpis': {}, 'meta': {'total_commentaires': 3}}

    monkeypatch.setattr(type(_app.gabriel), 'run_psycho', fake_run_psycho)
    monkeypatch.setattr(_db, 'check_usage_limit',
                        lambda uid, email=None: {'allowed': True})
    monkeypatch.setattr(_db, 'save_analysis', lambda entry, uid, folder_id=None: None)

    c = _client()
    r = c.post('/analyze',
               data=json.dumps({'source': 'text',
                                'content': 'Un commentaire\nDeux commentaires\nTrois commentaires'}),
               content_type='application/json')
    d = r.get_json()
    assert r.status_code == 200
    job_id = d['job_id']

    import time
    for _ in range(50):
        job = _app._jobs.get(job_id)
        if job and job['status'] in ('done', 'error'):
            break
        time.sleep(0.1)

    assert _app._jobs[job_id]['status'] == 'done'
    assert captured.get('seen_before_done') is True
    _assert_psychologist_debit(funded_credit_store)
    _app._jobs.pop(job_id, None)


# ════════════════════════════════════════════════════════════════════════════
# 13. /analyze renvoie 403 + limit_reached quand check_usage_limit refuse
# ════════════════════════════════════════════════════════════════════════════
def test_analyze_blocked_at_usage_limit(monkeypatch):
    monkeypatch.setattr(_db, 'check_usage_limit',
                        lambda uid, email=None: {
                            'allowed': False, 'reason': 'limit',
                            'used': 3, 'limit': 3, 'plan': 'free',
                        })

    c = _client()
    r = c.post('/analyze',
               data=json.dumps({'source': 'text',
                                'content': 'Un commentaire\nDeux commentaires\nTrois commentaires'}),
               content_type='application/json')
    d = r.get_json()
    assert r.status_code == 403
    assert d['error'] == 'limit_reached'
    assert d['upgrade_required'] is True
    assert d['analyses_used'] == 3
    assert d['analyses_limit'] == 3
    assert d['plan'] == 'free'
