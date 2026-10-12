# ─── Gabriel — Tests import fichiers commentaires (CSV / Excel / JSON / TXT) ──
#
# Couvre le parsing, la détection de colonnes, la normalisation, les limites
# de sécurité et l'intégration avec /analyze (source='file').
# Lancer : cd /Users/easycash/Desktop/Gabriel && venv/bin/pytest tests/test_file_import.py -v

import io
import os
import sys
import json
import pytest

os.environ['AUTH_ENABLED']       = 'true'
os.environ['FLASK_SECRET_KEY']   = 'test-secret-for-file-import'
os.environ.setdefault('MISTRAL_API_KEY', 'test-key')
os.environ.setdefault('SUPABASE_URL', '')
os.environ.setdefault('SUPABASE_KEY', '')
os.environ['RATE_LIMIT_ENABLED'] = 'false'

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import app as _app
import api.db as _db
from services.file_importer import (
    parse_comments_file, normalize_comment_items, FileImportError,
)

UID = 'test-uid-files'


def _client():
    c = _app.app.test_client()
    with c.session_transaction() as s:
        s['user_id']    = UID
        s['user_email'] = 'files@example.com'
        s['user_name']  = 'File Tester'
    return c


def _upload(filename, content_bytes, column=None):
    data = {'file': (io.BytesIO(content_bytes), filename)}
    if column:
        data['column'] = column
    return _client().post('/upload-comments-file', data=data,
                          content_type='multipart/form-data')


@pytest.fixture
def funded_credit_store(monkeypatch, tmp_path):
    """Compte local isolé : les tests /analyze exercent le vrai débit."""
    users_file = tmp_path / 'users.json'
    users_file.write_text(
        json.dumps({
            UID: {
                'user_id': UID,
                'email': 'files@example.com',
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
# 1. CSV simple (virgule)
# ════════════════════════════════════════════════════════════════════════════
def test_csv_simple():
    csv_data = "comment,likes\nTrès bon service,12\nPrix pas clair du tout,3\nExcellent produit vraiment,7\n"
    r = _upload('avis.csv', csv_data.encode('utf-8'))
    d = r.get_json()
    assert r.status_code == 200
    assert d['success'] is True
    assert d['file_type'] == 'csv'
    assert d['selected_column'] == 'comment'
    assert d['comments_count'] == 3
    assert d['normalized_comments'][0]['likes'] == 12
    assert d['normalized_comments'][0]['source'] == 'file_upload'


# ════════════════════════════════════════════════════════════════════════════
# 2. CSV point-virgule
# ════════════════════════════════════════════════════════════════════════════
def test_csv_semicolon():
    csv_data = "avis;note\nProduit conforme à la description;5\nLivraison trop lente hélas;2\nTrès satisfait de mon achat;5\n"
    r = _upload('export.csv', csv_data.encode('utf-8'))
    d = r.get_json()
    assert d['success'] is True
    assert d['selected_column'] == 'avis'
    assert d['comments_count'] == 3
    assert d['normalized_comments'][0]['rating'] == 5.0


# ════════════════════════════════════════════════════════════════════════════
# 3. CSV latin-1 (fallback encodage)
# ════════════════════════════════════════════════════════════════════════════
def test_csv_latin1():
    csv_data = "commentaire\nTrès déçu de la qualité\nÉchange rapide et efficace\nProduit cassé à l'arrivée\n"
    r = _upload('avis.csv', csv_data.encode('latin-1'))
    d = r.get_json()
    assert d['success'] is True
    assert d['comments_count'] == 3


# ════════════════════════════════════════════════════════════════════════════
# 4. Excel avec colonne commentaire
# ════════════════════════════════════════════════════════════════════════════
def test_excel_xlsx():
    import pandas as pd
    df = pd.DataFrame({
        'review': ['Excellent rapport qualité prix', 'Trop cher pour ce que c est', 'Je recommande vivement'],
        'rating': [5, 2, 4],
    })
    buf = io.BytesIO()
    df.to_excel(buf, index=False, engine='openpyxl')
    r = _upload('reviews.xlsx', buf.getvalue())
    d = r.get_json()
    assert d['success'] is True
    assert d['file_type'] == 'xlsx'
    assert d['selected_column'] == 'review'
    assert d['comments_count'] == 3
    assert d['normalized_comments'][1]['rating'] == 2.0


# ════════════════════════════════════════════════════════════════════════════
# 5. JSON tableau d'objets
# ════════════════════════════════════════════════════════════════════════════
def test_json_array_of_objects():
    payload = [
        {'comment': 'Très bon service client', 'likes': 12},
        {'comment': 'Prix pas clair sur le site', 'likes': 3},
        {'comment': 'Interface agréable et rapide', 'likes': 8},
    ]
    r = _upload('data.json', json.dumps(payload).encode('utf-8'))
    d = r.get_json()
    assert d['success'] is True
    assert d['file_type'] == 'json'
    assert d['comments_count'] == 3
    assert d['normalized_comments'][0]['likes'] == 12


# ════════════════════════════════════════════════════════════════════════════
# 6. JSON objet englobant {"reviews": [...]}
# ════════════════════════════════════════════════════════════════════════════
def test_json_wrapped_reviews():
    payload = {'reviews': [
        {'text': 'Excellent produit vraiment top', 'rating': 5},
        {'text': 'Trop cher à mon avis', 'rating': 2},
        {'text': 'Correct sans plus honnêtement', 'rating': 3},
    ]}
    r = _upload('reviews.json', json.dumps(payload).encode('utf-8'))
    d = r.get_json()
    assert d['success'] is True
    assert d['comments_count'] == 3
    assert d['normalized_comments'][0]['rating'] == 5.0


# ════════════════════════════════════════════════════════════════════════════
# 7. JSON tableau de strings
# ════════════════════════════════════════════════════════════════════════════
def test_json_array_of_strings():
    payload = ['Super expérience d achat', 'Déception totale sur la livraison', 'Bon rapport qualité prix']
    r = _upload('comments.json', json.dumps(payload).encode('utf-8'))
    d = r.get_json()
    assert d['success'] is True
    assert d['comments_count'] == 3


# ════════════════════════════════════════════════════════════════════════════
# 8. TXT — une ligne = un commentaire
# ════════════════════════════════════════════════════════════════════════════
def test_text_file_one_comment_per_line():
    text_data = "Très bon service client\nPrix trop élevé pour moi\nJe recommande sans hésiter\n"
    r = _upload('commentaires.txt', text_data.encode('utf-8'))
    d = r.get_json()
    assert r.status_code == 200
    assert d['success'] is True
    assert d['file_type'] == 'txt'
    assert d['comments_count'] == 3
    assert d['normalized_comments'][1]['text'] == 'Prix trop élevé pour moi'


# ════════════════════════════════════════════════════════════════════════════
# 8. Fichier sans colonne exploitable
# ════════════════════════════════════════════════════════════════════════════
def test_no_usable_column():
    csv_data = "id,qty\n1,2\n2,5\n3,1\n"
    r = _upload('stock.csv', csv_data.encode('utf-8'))
    d = r.get_json()
    assert r.status_code == 400
    assert d['success'] is False
    assert 'colonne' in d['error'].lower()


# ════════════════════════════════════════════════════════════════════════════
# 9. Doublons supprimés + lignes vides ignorées
# ════════════════════════════════════════════════════════════════════════════
def test_duplicates_and_empty_removed():
    items = [
        {'text': 'Très bon produit'},
        {'text': 'Très bon produit'},       # doublon exact
        {'text': '  très BON produit  '},   # doublon après normalisation
        {'text': ''},                        # vide
        {'text': 'ok'},                      # trop court (< 3)
        {'text': 'Autre commentaire valide'},
    ]
    normalized = normalize_comment_items(items, source_file='t.csv')
    assert len(normalized) == 2
    assert normalized[0]['text'] == 'Très bon produit'


# ════════════════════════════════════════════════════════════════════════════
# 10. Neutralisation des formules Excel + troncature textes longs
# ════════════════════════════════════════════════════════════════════════════
def test_formula_neutralized_and_truncation():
    items = [
        {'text': '=SUM(A1:A9) commentaire piégé'},
        {'text': '@import malicieux ici'},
        {'text': 'x' * 5000},
    ]
    normalized = normalize_comment_items(items)
    assert normalized[0]['text'].startswith('SUM')
    assert normalized[1]['text'].startswith('import')
    assert len(normalized[2]['text']) == 2000


# ════════════════════════════════════════════════════════════════════════════
# 11. Limite de taille (> 5 MB refusé)
# ════════════════════════════════════════════════════════════════════════════
def test_file_too_large():
    big = b'comment\n' + (b'a' * 100 + b'\n') * 60000  # ~6 MB
    r = _upload('big.csv', big)
    d = r.get_json()
    assert r.status_code == 413
    assert 'lourd' in d['error'].lower()


# ════════════════════════════════════════════════════════════════════════════
# 12. Extension refusée
# ════════════════════════════════════════════════════════════════════════════
def test_bad_extension():
    r = _upload('script.exe', b'MZ...')
    d = r.get_json()
    assert r.status_code == 400
    assert d['success'] is False


# ════════════════════════════════════════════════════════════════════════════
# 13. Auth requise
# ════════════════════════════════════════════════════════════════════════════
def test_upload_requires_auth():
    c = _app.app.test_client()  # pas de session
    r = c.post('/upload-comments-file',
               data={'file': (io.BytesIO(b'comment\nabc def ghi\n'), 'a.csv')},
               content_type='multipart/form-data')
    assert r.status_code in (302, 401)


# ════════════════════════════════════════════════════════════════════════════
# 14. Choix de colonne forcé (param column)
# ════════════════════════════════════════════════════════════════════════════
def test_forced_column():
    csv_data = ("comment,response\n"
                "Court,Réponse détaillée numéro un vraiment complète\n"
                "Bref,Une autre réponse très détaillée et longue\n"
                "Oui déjà,Troisième réponse encore plus détaillée ici\n")
    r = _upload('multi.csv', csv_data.encode('utf-8'), column='response')
    d = r.get_json()
    assert d['success'] is True
    assert d['selected_column'] == 'response'
    assert 'comment' in d['detected_columns'] and 'response' in d['detected_columns']


# ════════════════════════════════════════════════════════════════════════════
# 15. Intégration /analyze avec source='file' (LLM mocké)
# ════════════════════════════════════════════════════════════════════════════
def test_analyze_with_file_source(monkeypatch, funded_credit_store):
    captured = {}

    def fake_run_psycho(self, comments, video_context='', title='', progress_cb=None, partial_cb=None):
        captured['comments'] = comments
        return {'kpis': {}, 'meta': {'total_commentaires': len(comments)}}

    monkeypatch.setattr(type(_app.gabriel), 'run_psycho', fake_run_psycho)
    monkeypatch.setattr(_db, 'check_usage_limit', lambda uid, email=None: {'allowed': True})
    monkeypatch.setattr(_db, 'save_analysis', lambda entry, uid, folder_id=None: None)

    comments = [
        {'text': 'Très bon service client', 'likes': 12},
        {'text': 'Prix pas clair du tout', 'likes': 3},
        {'text': 'Interface rapide et agréable', 'likes': 8},
    ]
    r = _client().post('/analyze',
                       data=json.dumps({'source': 'file', 'content': 'avis.csv',
                                        'comments': comments}),
                       content_type='application/json')
    d = r.get_json()
    assert r.status_code == 200
    assert d.get('job_id')

    import time
    for _ in range(50):
        job = _app._jobs.get(d['job_id'])
        if job and job['status'] in ('done', 'error'):
            break
        time.sleep(0.1)
    assert _app._jobs[d['job_id']]['status'] == 'done'
    assert len(captured['comments']) == 3
    assert captured['comments'][0]['text'] == 'Très bon service client'
    assert captured['comments'][0]['likes'] == 12
    _assert_psychologist_debit(funded_credit_store)
    _app._jobs.pop(d['job_id'], None)


# ════════════════════════════════════════════════════════════════════════════
# 16. /analyze source='file' avec payload malveillant → sanitisé
# ════════════════════════════════════════════════════════════════════════════
def test_analyze_file_source_sanitizes_payload(monkeypatch, funded_credit_store):
    captured = {}

    def fake_run_psycho(self, comments, video_context='', title='', progress_cb=None, partial_cb=None):
        captured['comments'] = comments
        return {'kpis': {}, 'meta': {'total_commentaires': len(comments)}}

    monkeypatch.setattr(type(_app.gabriel), 'run_psycho', fake_run_psycho)
    monkeypatch.setattr(_db, 'check_usage_limit', lambda uid, email=None: {'allowed': True})
    monkeypatch.setattr(_db, 'save_analysis', lambda entry, uid, folder_id=None: None)

    comments = [
        {'text': '=HYPERLINK("http://evil") cliquez ici', 'likes': 'not_a_number'},
        {'text': 'Commentaire normal tout à fait valide'},
        'Un simple string aussi accepté',
        {'text': 'x' * 10000},
        {'no_text_key': 'ignoré'},
    ]
    r = _client().post('/analyze',
                       data=json.dumps({'source': 'file', 'content': 'sus.json',
                                        'comments': comments}),
                       content_type='application/json')
    d = r.get_json()
    assert r.status_code == 200

    import time
    for _ in range(50):
        job = _app._jobs.get(d['job_id'])
        if job and job['status'] in ('done', 'error'):
            break
        time.sleep(0.1)
    sent = captured['comments']
    texts = [c['text'] for c in sent]
    assert all(not t.startswith('=') for t in texts)        # formule neutralisée
    assert all(len(t) <= 2000 for t in texts)               # troncature
    assert sent[0]['likes'] == 0                            # likes invalide → 0
    assert len(sent) == 4                                   # item sans text ignoré
    _assert_psychologist_debit(funded_credit_store)
    _app._jobs.pop(d['job_id'], None)


# ════════════════════════════════════════════════════════════════════════════
# 17. Mode copier-coller toujours fonctionnel (non-régression)
# ════════════════════════════════════════════════════════════════════════════
def test_manual_paste_still_works(monkeypatch, funded_credit_store):
    def fake_run_psycho(self, comments, video_context='', title='', progress_cb=None, partial_cb=None):
        return {'kpis': {}, 'meta': {'total_commentaires': len(comments)}}

    monkeypatch.setattr(type(_app.gabriel), 'run_psycho', fake_run_psycho)
    monkeypatch.setattr(_db, 'check_usage_limit', lambda uid, email=None: {'allowed': True})
    monkeypatch.setattr(_db, 'save_analysis', lambda entry, uid, folder_id=None: None)

    r = _client().post('/analyze',
                       data=json.dumps({'source': 'text',
                                        'content': 'Premier commentaire ici\nDeuxième commentaire là\nTroisième commentaire enfin'}),
                       content_type='application/json')
    d = r.get_json()
    assert r.status_code == 200
    assert d.get('job_id')

    import time
    for _ in range(50):
        job = _app._jobs.get(d['job_id'])
        if job and job['status'] in ('done', 'error'):
            break
        time.sleep(0.1)
    assert _app._jobs[d['job_id']]['status'] == 'done'
    _assert_psychologist_debit(funded_credit_store)
    _app._jobs.pop(d['job_id'], None)
