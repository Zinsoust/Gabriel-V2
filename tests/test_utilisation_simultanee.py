"""Deux utilisateurs qui travaillent en même temps ne se mélangent jamais.

Le serveur tourne avec un seul worker et plusieurs threads : les travaux en cours
(_jobs) et le cache d'analyses (_psycho_cache) sont partagés entre tous les
utilisateurs. Ce test lance des générations réellement simultanées, dont le
contenu dépend de l'utilisateur, et vérifie que chacun ne récupère que le sien.
"""
import os
import threading
import time

os.environ.setdefault('FLASK_SECRET_KEY', 'test-secret-simultane-suffisamment-long')
os.environ.setdefault('MISTRAL_API_KEY', 'test-key')
os.environ.setdefault('SUPABASE_URL', '')
os.environ.setdefault('SUPABASE_KEY', '')
os.environ['RATE_LIMIT_ENABLED'] = 'false'

import api.db as _db
import app as _app

UTILISATEURS = ['simultane-A', 'simultane-B', 'simultane-C']


def _client(uid):
    c = _app.app.test_client()
    with c.session_transaction() as s:
        s['user_id'] = uid; s['user_email'] = f'{uid}@example.com'
    return c


def test_des_generations_simultanees_restent_chacune_a_leur_proprietaire(monkeypatch):
    monkeypatch.setenv('AUTH_ENABLED', 'true')
    monkeypatch.setattr(_db, 'has_enough_credits', lambda *a, **k: True)
    monkeypatch.setattr(_db, 'deduct_credits', lambda *a, **k: None)
    monkeypatch.setattr(_db, 'create_job', lambda *a, **k: True)
    monkeypatch.setattr(_db, 'update_job', lambda *a, **k: True)
    monkeypatch.setattr(_db, 'get_job', lambda *a, **k: None)
    monkeypatch.setattr(_app, '_resolve_psycho', lambda d, u: {'brief': {'qui': f'audience de {u}'}})
    monkeypatch.setattr(_app, '_resolve_strategy', lambda d, u: {})
    monkeypatch.setattr(_app, '_resolve_business_context', lambda d, u: {})
    import agents.creation as creation

    depart = threading.Barrier(len(UTILISATEURS))
    liberer = threading.Event()             # les générations restent en cours tant qu'on ne les libère pas

    def faux_generate(on_stage=None, **kw):
        # Chaque génération dure un temps différent : elles se chevauchent réellement.
        proprietaire = kw['psycho_data']['brief']['qui']
        depart.wait(timeout=10)
        liberer.wait(timeout=20)
        time.sleep(0.05 * (1 + UTILISATEURS.index(proprietaire.split(' de ')[1])))
        return {'content': {'texte': f'Texte écrit pour {proprietaire}'}, 'full_text': f'Texte écrit pour {proprietaire}', 'success': True}
    monkeypatch.setattr(creation, 'generate_result', faux_generate)

    jobs = {}
    for uid in UTILISATEURS:
        r = _client(uid).post('/api/v2/agents/createur/generate', json={'content_type': 'youtube', 'user_request': f'Demande de {uid}'})
        assert r.status_code == 200
        jobs[uid] = r.get_json()['job_id']
    assert len(set(jobs.values())) == len(UTILISATEURS)                   # des identifiants distincts

    # Pendant que les générations sont en cours, un autre utilisateur ne peut ni les lire ni les deviner.
    intrus = _client('simultane-B').get(f"/api/v2/jobs/{jobs['simultane-A']}")
    assert intrus.status_code == 404 and 'running' not in intrus.get_data(as_text=True)
    assert _client('simultane-A').get(f"/api/v2/jobs/{jobs['simultane-A']}").get_json()['status'] == 'running'
    liberer.set()

    resultats, erreurs = {}, []

    def suivre(uid):
        c = _client(uid)
        for _ in range(200):
            d = c.get(f'/api/v2/jobs/{jobs[uid]}').get_json()
            if d['status'] == 'done':
                resultats[uid] = d['data']; return
            time.sleep(0.02)
        erreurs.append(f'{uid} : jamais terminé')

    fils = [threading.Thread(target=suivre, args=(u,)) for u in UTILISATEURS]
    [f.start() for f in fils]; [f.join(timeout=30) for f in fils]

    assert not erreurs, erreurs
    for uid in UTILISATEURS:
        assert resultats[uid]['full_text'] == f'Texte écrit pour audience de {uid}', f"{uid} a reçu le texte d'un autre"
