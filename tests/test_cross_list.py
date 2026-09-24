"""Liste des Cross Analyses pour le menu : cloisonnée par utilisateur, légère."""
import os
os.environ.setdefault('FLASK_SECRET_KEY', 'test-secret-cross-list')
os.environ.setdefault('MISTRAL_API_KEY', 'test-key')
import app as _app
import api.db as _db


def test_la_liste_ne_montre_que_les_comparaisons_de_l_utilisateur(monkeypatch, tmp_path):
    lignes = [
        {'cross_analysis_id': 'c-moi', 'user_id': 'u-moi', 'status': 'completed', 'created_at': '2026-09-14T10:00:00',
         'source_records': [{'source_snapshot': {'label': 'A', 'metadata': {'title': 'IA locale'}}},
                            {'source_snapshot': {'label': 'B', 'metadata': {'title': 'IA pour débutants'}}}],
         'result_data': {'enorme': 'x' * 1000}},
        {'cross_analysis_id': 'c-autre', 'user_id': 'u-autre', 'status': 'completed', 'created_at': '2026-09-14T11:00:00', 'source_records': []},
    ]
    monkeypatch.setattr(_db, '_supabase', None)
    monkeypatch.setattr(_db, '_load_json_cross_analyses', lambda: lignes)
    client = _app.app.test_client()
    with client.session_transaction() as s:
        s['user_id'] = 'u-moi'; s['user_email'] = 'moi@example.com'
    r = client.get('/api/v2/agents/psychologue/cross-analyses')
    assert r.status_code == 200
    liste = r.get_json()['cross_analyses']
    assert [c['cross_analysis_id'] for c in liste] == ['c-moi']
    assert [s['title'] for s in liste[0]['sources']] == ['IA locale', 'IA pour débutants']
    assert 'result_data' not in liste[0]
