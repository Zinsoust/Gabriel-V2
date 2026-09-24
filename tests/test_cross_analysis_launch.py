"""Route de lancement Cross : orchestration asynchrone sans LLM ni réseau."""

import os
import sys
import time

os.environ['AUTH_ENABLED'] = 'true'
os.environ['FLASK_SECRET_KEY'] = 'test-secret-cross-launch'
os.environ.setdefault('MISTRAL_API_KEY', 'test-key')
os.environ.setdefault('SUPABASE_URL', '')
os.environ.setdefault('SUPABASE_KEY', '')
os.environ['RATE_LIMIT_ENABLED'] = 'false'
os.environ['NLP_PRELOAD'] = 'false'

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import app as app_module


def _client():
    client = app_module.app.test_client()
    with client.session_transaction() as session:
        session['user_id'] = 'cross-launch-user'
        session['user_email'] = 'cross-launch@example.com'
    return client


def test_cross_launch_runs_as_job_and_preserves_the_simple_pipeline_boundary(monkeypatch):
    stored = {}

    def fake_create(cross_id, user_id, sources, **kwargs):
        stored[cross_id] = {
            'cross_analysis_id': cross_id, 'user_id': user_id, 'job_id': kwargs['job_id'],
            'status': 'prepared', 'result_data': {'source_definitions': sources}, 'source_records': [],
        }
        return False

    def fake_update(cross_id, user_id, **fields):
        stored[cross_id].update(fields)
        return True

    def fake_pipeline(sources, options, analyze_source, *, progress_cb=None, source_status_cb=None):
        if progress_cb:
            progress_cb('comparaison', 88)
        analyses = []
        for source in sources:
            analysis = {
                'source_id': source['source_id'], 'analysis_id': f"a-{source['position']}",
                'metadata': {}, 'dataset': {}, 'data_quality': {}, 'personas': [],
            }
            analyses.append(analysis)
            if source_status_cb:
                source_status_cb(source, 'completed', analysis)
        return {
            'status': 'completed', 'source_analyses': analyses, 'cross_summary': {'sources_count': 2},
            'technical_summary': {}, 'common_psychological_core': {}, 'confidence': {},
        }

    monkeypatch.setattr(app_module._db, 'check_usage_limit', lambda *_args, **_kwargs: {'allowed': True, 'plan': 'dev'})
    monkeypatch.setattr(app_module._db, 'has_enough_credits', lambda *_args, **_kwargs: True)
    monkeypatch.setattr(app_module._db, 'create_cross_analysis', fake_create)
    monkeypatch.setattr(app_module._db, 'update_cross_analysis', fake_update)
    monkeypatch.setattr(app_module._db, 'create_job', lambda *_args, **_kwargs: False)
    monkeypatch.setattr(app_module._db, 'update_cross_analysis_source', lambda *_args, **_kwargs: True)
    monkeypatch.setattr(app_module._db, 'save_analysis', lambda *_args, **_kwargs: None)
    monkeypatch.setattr(app_module._db, 'deduct_credits', lambda *_args, **_kwargs: True)
    monkeypatch.setattr(app_module, 'interpret_cross_analysis', lambda _result: {'status': 'completed'})
    monkeypatch.setattr(app_module, 'run_dialectic_review', lambda *_args: {'status': 'completed'})
    monkeypatch.setattr(app_module, 'apply_cross_interpretation', lambda result, *_args: result)
    monkeypatch.setattr(app_module, 'synthesize_cross', lambda _result: {'status': 'unavailable'})
    monkeypatch.setattr(app_module._cross_pipeline, 'run', fake_pipeline)

    response = _client().post('/api/v2/agents/psychologue/cross-analyses', json={'sources': [
        {'url': 'https://www.youtube.com/watch?v=dQw4w9WgXcQ'},
        {'url': 'https://youtu.be/9bZkp7q19f0'},
    ]})
    payload = response.get_json()

    assert response.status_code == 202
    assert payload['analysis_mode'] == 'cross'
    for _ in range(20):
        job = app_module._jobs[payload['job_id']]
        if job['status'] == 'done':
            break
        time.sleep(0.01)
    assert app_module._jobs[payload['job_id']]['status'] == 'done'
    assert stored[payload['cross_analysis_id']]['status'] == 'completed'

    # model_version doit refléter les modèles Mistral réellement appelés
    # (core.analyzer.MISTRAL_MODELS), pas une variable d'environnement que le
    # code d'appel LLM ne lisait jamais. embedding_version doit être honnête :
    # la Cross ne calcule aucun embedding aujourd'hui, ça doit se lire comme
    # tel, pas comme un champ vide qu'on aurait simplement oublié de remplir.
    assert stored[payload['cross_analysis_id']]['model_version'] == '+'.join(
        app_module.MISTRAL_MODELS.values()
    )
    assert stored[payload['cross_analysis_id']]['embedding_version'] == 'not_used_in_cross_v1'


def test_cross_failure_never_leaks_the_raw_exception_to_the_client(monkeypatch):
    """Une Cross qui échoue doit persister un message générique en base, jamais
    str(exc) — sinon un client qui relit le statut après un redémarrage/éviction
    du job en mémoire reçoit l'exception brute (chemins, params internes...)."""
    stored = {}
    SENSITIVE = "connection to internal-db-host.render.internal:5432 refused (user=gabriel_prod)"

    def fake_create(cross_id, user_id, sources, **kwargs):
        stored[cross_id] = {
            'cross_analysis_id': cross_id, 'user_id': user_id, 'job_id': kwargs['job_id'],
            'status': 'prepared', 'result_data': {'source_definitions': sources}, 'source_records': [],
        }
        return False

    def fake_update(cross_id, user_id, **fields):
        stored[cross_id].update(fields)
        return True

    def failing_pipeline(*_args, **_kwargs):
        raise RuntimeError(SENSITIVE)

    monkeypatch.setattr(app_module._db, 'check_usage_limit', lambda *_args, **_kwargs: {'allowed': True, 'plan': 'dev'})
    monkeypatch.setattr(app_module._db, 'has_enough_credits', lambda *_args, **_kwargs: True)
    monkeypatch.setattr(app_module._db, 'create_cross_analysis', fake_create)
    monkeypatch.setattr(app_module._db, 'update_cross_analysis', fake_update)
    monkeypatch.setattr(app_module._db, 'create_job', lambda *_args, **_kwargs: False)
    monkeypatch.setattr(app_module._db, 'update_job', lambda *_args, **_kwargs: True)
    monkeypatch.setattr(app_module._cross_pipeline, 'run', failing_pipeline)

    response = _client().post('/api/v2/agents/psychologue/cross-analyses', json={'sources': [
        {'url': 'https://www.youtube.com/watch?v=dQw4w9WgXcQ'},
        {'url': 'https://youtu.be/9bZkp7q19f0'},
    ]})
    payload = response.get_json()
    job_id = payload['job_id']
    cross_id = payload['cross_analysis_id']

    for _ in range(50):
        if app_module._jobs[job_id]['status'] == 'error':
            break
        time.sleep(0.01)
    assert app_module._jobs[job_id]['status'] == 'error'
    assert SENSITIVE not in app_module._jobs[job_id].get('error', '')

    # Ce que la base a réellement gardé — c'est CE champ que
    # _cross_job_state() sert au client une fois le job hors mémoire.
    assert SENSITIVE not in stored[cross_id].get('error_message', '')

    # Simule un redémarrage serveur / éviction du job en mémoire, puis relit
    # le statut exactement comme le ferait le client après coup.
    app_module._jobs.pop(job_id, None)
    monkeypatch.setattr(app_module._db, 'get_cross_analysis', lambda *_a, **_k: stored[cross_id])

    response = _client().get(f'/api/v2/agents/psychologue/cross-analyses/{cross_id}/status')
    body_text = response.get_data(as_text=True)
    assert SENSITIVE not in body_text


def test_cross_status_recovers_from_a_server_restart_instead_of_staying_running(monkeypatch):
    """Reproduit le bug : le thread en mémoire est perdu (redémarrage serveur),
    mais la Cross reste bloquée sur 'running' en base pour toujours."""
    updates = []

    def fake_update(cross_id, user_id, **fields):
        updates.append(fields)
        return True

    monkeypatch.setattr(app_module._db, 'get_cross_analysis', lambda *_a, **_k: {
        'cross_analysis_id': 'cross_orphaned', 'user_id': 'cross-launch-user',
        'job_id': 'job-not-in-memory', 'status': 'running', 'result_data': {}, 'source_records': [],
    })
    monkeypatch.setattr(app_module._db, 'update_cross_analysis', fake_update)
    # Le job n'existe plus dans _jobs : c'est exactement ce qui se produit
    # après un redémarrage serveur (worker unique, thread perdu).
    app_module._jobs.pop('job-not-in-memory', None)

    response = _client().get('/api/v2/agents/psychologue/cross-analyses/cross_orphaned/status')
    payload = response.get_json()

    assert response.status_code == 200
    assert payload['status'] == 'interrupted'
    assert updates and updates[0].get('status') == 'interrupted'


def test_cross_reuse_gives_each_session_its_own_identity_and_does_not_rebill_cached_sources(monkeypatch):
    """Bout-en-bout, avec le vrai pipeline (pas de mock de `_cross_pipeline.run`) :
    relancer une Cross sur les deux mêmes vidéos, même utilisateur, doit :
      - éviter un second appel LLM (le cache profite toujours à la performance) ;
      - donner à la seconde session son PROPRE analysis_id par source, jamais
        celui de la première (traçabilité) ;
      - ne pas débiter de crédits pour les sources entièrement réutilisées."""
    stored = {}
    saved_analyses = []
    deductions = []

    def fake_create(cross_id, user_id, sources, **kwargs):
        stored[cross_id] = {
            'cross_analysis_id': cross_id, 'user_id': user_id, 'job_id': kwargs['job_id'],
            'status': 'prepared', 'result_data': {'source_definitions': sources}, 'source_records': [],
        }
        return False

    def fake_update(cross_id, user_id, **fields):
        stored[cross_id].update(fields)
        return True

    def fake_save_analysis(record, user_id, folder_id=None):
        saved_analyses.append({**record, 'user_id': user_id, 'folder_id': folder_id})

    def fake_deduct_credits(user_id, amount, reason=''):
        deductions.append({'user_id': user_id, 'amount': amount, 'reason': reason})
        return True

    llm_calls = []

    def fake_run_psycho(self, comments, video_context='', title='', progress_cb=None, partial_cb=None):
        llm_calls.append(title)
        return {
            'meta': {'total_commentaires': len(comments), 'commentaires_analyses': len(comments)},
            'dashboard': {
                'confidence_score': 70, 'noise_ratio': 2,
                'emotion_distribution': {'Espoir': 60}, 'sujets_recurrents': [],
            },
            'psychologie': {}, 'aspirations': {}, 'personas': [], 'interpretation': {}, 'kpis': {},
        }

    def fake_collect(source, *, max_comments, include_replies=False):
        video_id = source['video_id']
        comments = [
            {'id': f'{video_id}-1', 'text': 'Bon contenu.', 'likes': 3},
            {'id': f'{video_id}-2', 'text': 'Toujours pertinent.', 'likes': 1},
        ][:max_comments]
        return comments, {'title': f'Vidéo {video_id}', 'channel': 'Gabriel'}

    monkeypatch.setattr(app_module._db, 'check_usage_limit', lambda *_args, **_kwargs: {'allowed': True, 'plan': 'dev'})
    monkeypatch.setattr(app_module._db, 'has_enough_credits', lambda *_args, **_kwargs: True)
    monkeypatch.setattr(app_module._db, 'create_cross_analysis', fake_create)
    monkeypatch.setattr(app_module._db, 'update_cross_analysis', fake_update)
    monkeypatch.setattr(app_module._db, 'create_job', lambda *_args, **_kwargs: False)
    monkeypatch.setattr(app_module._db, 'update_cross_analysis_source', lambda *_args, **_kwargs: True)
    monkeypatch.setattr(app_module._db, 'save_cross_source_comments', lambda *_args, **_kwargs: True)
    monkeypatch.setattr(app_module._db, 'save_analysis', fake_save_analysis)
    monkeypatch.setattr(app_module._db, 'deduct_credits', fake_deduct_credits)
    monkeypatch.setattr(app_module, 'interpret_cross_analysis', lambda _result: {'status': 'completed'})
    monkeypatch.setattr(app_module, 'run_dialectic_review', lambda *_args: {'status': 'completed'})
    monkeypatch.setattr(app_module, 'apply_cross_interpretation', lambda result, *_args: result)
    monkeypatch.setattr(app_module, 'synthesize_cross', lambda _result: {'status': 'unavailable'})
    monkeypatch.setattr(type(app_module.gabriel), 'run_psycho', fake_run_psycho)
    monkeypatch.setattr(app_module._cross_pipeline.youtube_provider, 'collect', fake_collect)

    sources_payload = {'sources': [
        {'url': 'https://www.youtube.com/watch?v=dQw4w9WgXcQ'},
        {'url': 'https://youtu.be/9bZkp7q19f0'},
    ]}

    def _run_cross():
        response = _client().post('/api/v2/agents/psychologue/cross-analyses', json=sources_payload)
        payload = response.get_json()
        assert response.status_code == 202
        for _ in range(50):
            job = app_module._jobs[payload['job_id']]
            if job['status'] == 'done':
                break
            time.sleep(0.01)
        assert app_module._jobs[payload['job_id']]['status'] == 'done'
        return payload['cross_analysis_id']

    first_cross_id = _run_cross()
    assert len(llm_calls) == 2
    assert len(deductions) == 1  # 2 sources fraîches facturées la première fois

    second_cross_id = _run_cross()
    assert len(llm_calls) == 2, "les deux vidéos sont déjà en cache : pas de second appel LLM"
    assert len(deductions) == 1, "aucune source réutilisée ne doit être débitée une seconde fois"

    assert len(saved_analyses) == 4, "chaque session persiste ses propres enregistrements (2 + 2)"
    by_cross = {}
    for row in saved_analyses:
        by_cross.setdefault(row['full_result']['cross_analysis_id'], []).append(row['analysis_id'])
    assert set(by_cross[first_cross_id]) & set(by_cross[second_cross_id]) == set(), (
        "la seconde session ne doit jamais réutiliser l'analysis_id de la première"
    )

