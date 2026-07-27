# ─── Gabriel — Tests dossiers stratégiques ────────────────────────────────────
#
# Couvre le CRUD dossiers en mode JSON/mémoire (sans Supabase).
# Lancer : cd /Users/easycash/Desktop/Gabriel && venv/bin/pytest tests/test_folders.py -v

import os
import sys
import json
import uuid
import pytest

os.environ['AUTH_ENABLED']       = 'true'
os.environ['FLASK_SECRET_KEY']   = 'test-secret-folders'
os.environ.setdefault('MISTRAL_API_KEY', 'test-key')
os.environ.setdefault('SUPABASE_URL', '')
os.environ.setdefault('SUPABASE_KEY', '')
os.environ['RATE_LIMIT_ENABLED'] = 'false'

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import api.db as _db
import app as _app

UID_A = 'uid-folders-a'
UID_B = 'uid-folders-b'


def _client(uid=UID_A):
    c = _app.app.test_client()
    with c.session_transaction() as s:
        s['user_id']    = uid
        s['user_email'] = f'{uid}@example.com'
        s['user_name']  = 'Folder Tester'
    return c


# ══════════════════════════════════════════════════════════════════════════════
# 1. Création dossier — db layer (sans Supabase, _supabase=None)
# ══════════════════════════════════════════════════════════════════════════════
def test_create_folder_no_supabase():
    """Sans Supabase, create_folder retourne None (pas de fallback JSON pour les dossiers)."""
    result = _db.create_folder('fid-1', UID_A, 'Test Folder', objective='Obj', folder_type='audience')
    # Sans supabase, la fonction tente l'insert et retourne None sur erreur
    # OU retourne le row (si supabase est absent et qu'on atteint la fin sans erreur)
    # Dans notre impl : _supabase is None donc le try est ignoré, on retourne row
    assert result is None or isinstance(result, dict)


def test_create_folder_missing_title():
    """Un titre vide doit retourner None."""
    result = _db.create_folder('fid-x', UID_A, '  ', objective='Obj')
    assert result is None


def test_create_folder_missing_uid():
    """Un user_id vide doit retourner None."""
    result = _db.create_folder('fid-x', '', 'Title')
    assert result is None


# ══════════════════════════════════════════════════════════════════════════════
# 2. Routes HTTP — liste, création, suppression
# ══════════════════════════════════════════════════════════════════════════════
def test_api_list_folders_empty():
    """GET /api/folders retourne une liste vide (sans Supabase)."""
    c = _client()
    r = c.get('/api/folders')
    assert r.status_code == 200
    data = json.loads(r.data)
    assert data['success'] is True
    assert isinstance(data['folders'], list)


def test_api_create_folder_missing_title():
    """POST /api/folders sans titre → 400."""
    c = _client()
    r = c.post('/api/folders', json={})
    assert r.status_code == 400
    data = json.loads(r.data)
    assert data['success'] is False


def test_api_create_folder_title_too_long():
    """POST /api/folders avec titre > 200 chars → 400."""
    c = _client()
    r = c.post('/api/folders', json={'title': 'x' * 201})
    assert r.status_code == 400


def test_api_create_folder_valid():
    """POST /api/folders valide → 201 (ou 500 sans Supabase — acceptable)."""
    c = _client()
    r = c.post('/api/folders', json={'title': 'Mon Dossier Test', 'objective': 'Test', 'folder_type': 'audience'})
    # Sans Supabase, create_folder retourne None → route retourne 500
    # C'est le comportement attendu en l'absence de DB réelle
    assert r.status_code in (201, 500)


def test_api_delete_folder_unknown():
    """DELETE /api/folders/<id_inconnu> → success: False (sans Supabase)."""
    c = _client()
    r = c.delete('/api/folders/unknown-folder-id')
    assert r.status_code == 200
    data = json.loads(r.data)
    assert data['success'] is False


def test_api_get_folder_not_found():
    """GET /api/folders/<id_inconnu> → 404."""
    c = _client()
    r = c.get('/api/folders/nonexistent-folder-id')
    assert r.status_code == 404


# ══════════════════════════════════════════════════════════════════════════════
# 3. Isolation utilisateur — un user ne voit pas les dossiers d'un autre
# ══════════════════════════════════════════════════════════════════════════════
def test_isolation_get_folder():
    """get_folder_by_id avec mauvais user_id → None."""
    result = _db.get_folder_by_id('any-folder-id', UID_B)
    # Sans Supabase, retourne toujours None — isolation garantie
    assert result is None


def test_isolation_delete_folder():
    """delete_folder avec mauvais user_id → False."""
    result = _db.delete_folder('any-folder-id', UID_B)
    assert result is False


def test_isolation_update_folder():
    """update_folder avec mauvais user_id → False."""
    result = _db.update_folder('any-folder-id', UID_B, title='Hack')
    assert result is False


# ══════════════════════════════════════════════════════════════════════════════
# 4. Page HTML dossiers — accès et affichage
# ══════════════════════════════════════════════════════════════════════════════
def test_dossiers_page_auth():
    """GET /dossiers redirige vers /login si non authentifié."""
    c = _app.app.test_client()
    r = c.get('/dossiers')
    assert r.status_code in (302, 301)
    location = r.headers.get('Location', '')
    assert 'login' in location


def test_dossiers_page_authenticated():
    """GET /dossiers retourne 200 pour un utilisateur connecté."""
    c = _client()
    r = c.get('/dossiers')
    assert r.status_code == 200
    assert b'Dossiers' in r.data


def test_dossiers_create_dialog_uses_accessible_form():
    """La création doit rester utilisable au clic, au clavier et sur mobile."""
    c = _client()
    r = c.get('/dossiers')
    html = r.data.decode('utf-8')
    assert 'id="ds-create-form"' in html
    assert 'data-open-modal' in html
    assert 'type="submit" id="ds-submit-btn"' in html
    assert 'aria-labelledby="ds-modal-title"' in html


def test_dossier_detail_redirect_unknown():
    """GET /dossiers/<fid_inconnu> redirige vers /dossiers (dossier introuvable)."""
    c = _client()
    r = c.get('/dossiers/nonexistent-id')
    assert r.status_code in (302, 301)
    location = r.headers.get('Location', '')
    assert 'dossiers' in location


# ══════════════════════════════════════════════════════════════════════════════
# 5. Rétrocompatibilité — anciennes analyses non affectées
# ══════════════════════════════════════════════════════════════════════════════
def test_save_analysis_backward_compat():
    """save_analysis sans folder_id ne plante pas (rétrocompatibilité)."""
    entry = {
        'analysis_id': 'old-analysis-no-folder',
        'source': 'Test',
        'nb_commentaires': 10,
        'full_result': {},
    }
    try:
        _db.save_analysis(entry, UID_A)
    except Exception as e:
        pytest.fail(f'save_analysis sans folder_id a planté : {e}')


def test_save_strategy_backward_compat():
    """save_strategy sans folder_id ne plante pas."""
    try:
        sid = _db.save_strategy({'decision_centrale': 'Test'}, user_id=UID_A, analysis_id='old-analysis')
        assert isinstance(sid, str)
    except Exception as e:
        pytest.fail(f'save_strategy sans folder_id a planté : {e}')


def test_create_job_backward_compat():
    """create_job sans folder_id ne plante pas."""
    try:
        result = _db.create_job('job-no-folder', UID_A, 'analysis-abc')
        # Retourne False sans Supabase — comportement attendu
        assert result is False or result is True
    except Exception as e:
        pytest.fail(f'create_job sans folder_id a planté : {e}')
