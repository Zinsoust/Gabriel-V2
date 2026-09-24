"""Étape 3 (24/09/2026) — les travaux longs survivent à un redémarrage sans mentir.

Trouvé en conditions réelles : 3 analyses et 1 Cross Analyse restées « en cours »
depuis août (jamais relues, donc jamais marquées interrompues) ; une génération du
Créateur interrompue parlait d'« analyse » et de « commentaires » ; l'écran du
Créateur abandonnait après 4 minutes alors qu'une génération en dure 4 à 6.
"""
import datetime
import os
import time

os.environ.setdefault('FLASK_SECRET_KEY', 'test-secret-jobs-3')
os.environ.setdefault('MISTRAL_API_KEY', 'test-key')
os.environ.setdefault('SUPABASE_URL', '')
os.environ.setdefault('SUPABASE_KEY', '')
os.environ['RATE_LIMIT_ENABLED'] = 'false'

import api.db as _db
import app as _app

UID = 'job-etape3-user'


def _client():
    c = _app.app.test_client()
    with c.session_transaction() as s:
        s['user_id'] = UID; s['user_email'] = 'j3@example.com'
    return c


# ── Message adapté au type de travail ───────────────────────────────────────

def test_une_generation_du_createur_interrompue_ne_parle_pas_d_analyse(monkeypatch):
    monkeypatch.setattr(_db, 'get_job', lambda job_id, user_id=None: {'job_id': job_id, 'user_id': user_id, 'status': 'running'})
    monkeypatch.setattr(_db, 'update_job', lambda *a, **k: True)
    d = _client().get('/api/v2/jobs/cr_perdu-123').get_json()
    assert d['status'] == 'interrupted'
    assert 'génération' in d['error'] and 'Relancez-la' in d['error']
    assert 'commentaires' not in d['error'] and 'analyse' not in d['error'].lower()


def test_la_base_garde_le_message_du_bon_type_de_travail(monkeypatch):
    ecrits = []
    monkeypatch.setattr(_db, 'get_job', lambda job_id, user_id=None: {'job_id': job_id, 'user_id': user_id, 'status': 'running'})
    monkeypatch.setattr(_db, 'update_job', lambda job_id, **k: ecrits.append(k) or True)
    _client().get('/api/v2/jobs/cr_perdu-456')
    assert 'génération' in ecrits[0]['error_message'] and 'analyse' not in ecrits[0]['error_message'].lower()


def test_une_analyse_interrompue_garde_son_message_habituel(monkeypatch):
    monkeypatch.setattr(_db, 'get_job', lambda job_id, user_id=None: {'job_id': job_id, 'user_id': user_id, 'status': 'interrupted'})
    d = _client().get('/api/v2/jobs/abc123def').get_json()
    assert d['status'] == 'interrupted'
    assert "L'analyse a été interrompue" in d['error'] and 'commentaires' in d['error']


# ── Balayage des orphelins ──────────────────────────────────────────────────

class _Table:
    def __init__(self, journal, table, rows):
        self.journal, self.table, self.rows = journal, table, rows
        self.calls = []

    def update(self, fields): self.calls.append(('update', fields)); return self
    def in_(self, col, values): self.calls.append(('in', col, values)); return self
    def lt(self, col, value): self.calls.append(('lt', col, value)); return self

    def execute(self):
        self.journal.append((self.table, self.calls))
        return type('R', (), {'data': self.rows})()


class _Supabase:
    def __init__(self):
        self.journal = []

    def table(self, name):
        return _Table(self.journal, name, [{'id': 1}, {'id': 2}] if name == _db._T_JOBS else [{'id': 9}])


def test_le_balayage_marque_interrompus_les_travaux_sans_battement_de_coeur(monkeypatch):
    faux = _Supabase()
    monkeypatch.setattr(_db, '_supabase', faux)
    counts = _db.mark_stale_jobs_interrupted(min_age_seconds=120)
    assert counts == {'jobs': 2, 'cross': 1}
    tables = {t: calls for t, calls in faux.journal}
    assert set(tables) == {_db._T_JOBS, _db._T_CROSS_ANALYSES}
    for calls in tables.values():
        assert ('in', 'status', ['pending', 'running']) in calls          # jamais les travaux terminés
        limite = [c for c in calls if c[0] == 'lt'][0]
        assert limite[1] == 'updated_at'
        age = datetime.datetime.utcnow() - datetime.datetime.fromisoformat(limite[2])
        assert 110 <= age.total_seconds() <= 130                            # 2 minutes de grâce
        assert [c for c in calls if c[0] == 'update'][0][1]['status'] == 'interrupted'


def test_le_balayage_ne_fait_rien_sans_base(monkeypatch):
    monkeypatch.setattr(_db, '_supabase', None)
    assert _db.mark_stale_jobs_interrupted() == {'jobs': 0, 'cross': 0}


def test_le_balayage_survit_a_une_erreur_de_base(monkeypatch):
    class Casse:
        def table(self, name): raise RuntimeError('base indisponible')
    monkeypatch.setattr(_db, '_supabase', Casse())
    assert _db.mark_stale_jobs_interrupted() == {'jobs': 0, 'cross': 0}


# ── Battement de cœur pendant une génération ────────────────────────────────

def test_chaque_etape_de_la_generation_bat_dans_la_base(monkeypatch):
    battements = []
    monkeypatch.setattr(_db, 'has_enough_credits', lambda *a, **k: True)
    monkeypatch.setattr(_db, 'deduct_credits', lambda *a, **k: None)
    monkeypatch.setattr(_db, 'create_job', lambda *a, **k: True)
    monkeypatch.setattr(_db, 'update_job', lambda job_id, **k: battements.append((job_id, k)) or True)
    monkeypatch.setattr(_app, '_resolve_psycho', lambda d, u: {})
    monkeypatch.setattr(_app, '_resolve_strategy', lambda d, u: {})
    monkeypatch.setattr(_app, '_resolve_business_context', lambda d, u: {})
    import agents.creation as creation

    def faux_generate(on_stage=None, **kw):
        on_stage('writing', 'Rédaction', 40)
        on_stage('dialectic', 'Critique', 70)
        return {'content': {'texte': 'ok'}, 'full_text': 'ok', 'success': True}
    monkeypatch.setattr(creation, 'generate_result', faux_generate)

    r = _client().post('/api/v2/agents/createur/generate', json={'content_type': 'youtube', 'user_request': 'Un script'})
    assert r.status_code == 200
    job_id = r.get_json()['job_id']
    for _ in range(60):
        if any(k.get('status') == 'completed' for _, k in battements):
            break
        time.sleep(0.05)
    etapes = [(k['progress'], k['step']) for j, k in battements if k.get('status') == 'running']
    assert (40, 'Rédaction') in etapes and (70, 'Critique') in etapes
    assert all(j == job_id for j, _ in battements)
