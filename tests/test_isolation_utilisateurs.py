"""Isolation entre utilisateurs — le préalable à toute ouverture au public.

La clé Supabase du serveur est une clé secrète qui contourne les règles d'accès
de la base : l'isolation repose donc UNIQUEMENT sur le code. Trouvé le 24/09/2026 :
les chemins de repli sur fichier local (utilisés quand Supabase échoue) lisaient,
listaient et supprimaient sans vérifier le propriétaire. Une panne de base aurait
laissé un utilisateur voir ou effacer les données d'un autre.
"""
import json
import os

import pytest

os.environ.setdefault('FLASK_SECRET_KEY', 'test-secret-isolation')
os.environ.setdefault('MISTRAL_API_KEY', 'test-key')
os.environ.setdefault('SUPABASE_URL', '')
os.environ.setdefault('SUPABASE_KEY', '')
os.environ['RATE_LIMIT_ENABLED'] = 'false'

import api.db as db

A, B = 'utilisateur-A', 'utilisateur-B'


@pytest.fixture
def repli_local(tmp_path, monkeypatch):
    """Base indisponible : tout passe par les fichiers locaux, dans un dossier jetable."""
    monkeypatch.setattr(db, '_supabase', None)
    monkeypatch.setattr(db, '_DATA_DIR', str(tmp_path))
    for nom, fichier in (('_HISTORY_FILE', 'history.json'), ('_STRATEGIES_FILE', 'strategies.json'),
                         ('_FEEDBACKS_FILE', 'feedbacks.json'), ('_CROSS_ANALYSES_FILE', 'cross.json')):
        monkeypatch.setattr(db, nom, str(tmp_path / fichier))
    monkeypatch.setenv('AUTH_ENABLED', 'true')
    return tmp_path


def _donnees_de_A():
    db.save_analysis({'analysis_id': 'analyse-de-A', 'video_title': 'Analyse confidentielle de A', 'source': 'x',
                      'full_result': {'brief': {'qui': 'Secret de A'}}}, user_id=A)
    sid = db.save_strategy({'decision_centrale': 'Stratégie secrète de A'}, user_id=A, analysis_id='analyse-de-A')
    return sid


def test_un_utilisateur_ne_liste_pas_l_historique_d_un_autre(repli_local):
    _donnees_de_A()
    assert [e['analysis_id'] for e in db.get_history(A)] == ['analyse-de-A']
    assert db.get_history(B) == []


def test_un_utilisateur_ne_lit_pas_l_analyse_ou_la_strategie_d_un_autre(repli_local):
    sid = _donnees_de_A()
    assert db.get_analysis_by_id('analyse-de-A', A)
    assert db.get_analysis_by_id('analyse-de-A', B) is None
    assert db.get_strategy_by_id(sid, A)
    assert db.get_strategy_by_id(sid, B) is None
    assert [s['strategy_id'] for s in db.get_strategies(A)] == [sid]
    assert db.get_strategies(B) == []


def test_un_utilisateur_ne_supprime_pas_les_donnees_d_un_autre(repli_local):
    sid = _donnees_de_A()
    assert db.delete_analysis('analyse-de-A', B) is False
    db.delete_strategy(sid, B)
    assert db.get_analysis_by_id('analyse-de-A', A), "l'analyse de A a été effacée par B"
    assert db.get_strategy_by_id(sid, A), "la stratégie de A a été effacée par B"
    assert db.delete_analysis('analyse-de-A', A) is True                    # le propriétaire, lui, peut
    assert db.get_analysis_by_id('analyse-de-A', A) is None


def test_un_utilisateur_ne_modifie_pas_l_analyse_d_un_autre(repli_local):
    _donnees_de_A()
    db.update_analysis_strategy('analyse-de-A', {'decision_centrale': 'Injection par B'}, 'strat-B', B)
    entree = db.get_analysis_by_id('analyse-de-A', A)
    assert not entree.get('strategie_result'), "B a écrit une stratégie dans l'analyse de A"


def test_sans_utilisateur_connecte_rien_n_est_visible_quand_l_authentification_est_active(repli_local):
    _donnees_de_A()
    assert db.get_history(None) == []
    assert db.get_strategies(None) == []


def test_en_developpement_sans_authentification_les_anciennes_donnees_locales_restent_visibles(repli_local, monkeypatch):
    """Pas de régression pour le poste de travail : sans authentification, les entrées
    sans propriétaire (« local » ou vide) écrites par d'anciennes versions restent visibles."""
    monkeypatch.setenv('AUTH_ENABLED', 'false')
    dev = 'dec0de00-0000-4000-8000-000000000001'
    with open(db._HISTORY_FILE, 'w', encoding='utf-8') as f:
        json.dump([{'analysis_id': 'ancienne', 'video_title': 'Ancienne analyse', 'user_id': 'local'},
                   {'analysis_id': 'sans-proprietaire', 'video_title': 'Sans propriétaire'}], f)
    with open(db._STRATEGIES_FILE, 'w', encoding='utf-8') as f:
        json.dump([{'strategy_id': 'ancienne-strat', 'user_id': 'local', 'strategy_result': {}}], f)
    assert {e['analysis_id'] for e in db.get_history(dev)} == {'ancienne', 'sans-proprietaire'}
    assert db.get_strategy_by_id('ancienne-strat', dev)
    assert [s['strategy_id'] for s in db.get_strategies(dev)] == ['ancienne-strat']


def test_les_commentaires_de_retour_et_les_cross_analyses_sont_cloisonnes(repli_local):
    db.save_feedback({'usefulness': 'utile', 'resultat': 'positif', 'comment': 'Retour confidentiel de A'}, user_id=A, analysis_id='analyse-de-A')
    assert db.get_feedbacks(A) and db.get_feedbacks(B) == []

    db.create_cross_analysis('cross_de_A', A, [{'source_id': 's1', 'title': 'Vidéo de A', 'platform': 'youtube'}], options={})
    assert db.get_cross_analysis('cross_de_A', A)
    assert db.get_cross_analysis('cross_de_A', B) is None
    assert [c['cross_analysis_id'] for c in db.list_cross_analyses(A)] == ['cross_de_A']
    assert db.list_cross_analyses(B) == []
    db.update_cross_analysis('cross_de_A', B, status='failed', error_message='écrit par B')
    assert db.get_cross_analysis('cross_de_A', A)['status'] != 'failed', "B a modifié la Cross Analyse de A"


# ── Par les vraies routes ───────────────────────────────────────────────────

def _client_de(uid):
    import app as _app
    c = _app.app.test_client()
    if uid:
        with c.session_transaction() as s:
            s['user_id'] = uid; s['user_email'] = f'{uid}@example.com'
    return c


def test_par_les_routes_un_utilisateur_ne_touche_pas_aux_donnees_d_un_autre(repli_local):
    sid = _donnees_de_A()
    a, b = _client_de(A), _client_de(B)

    assert a.get('/history/analyse-de-A/load').status_code == 200
    assert a.get(f'/strategies/{sid}').status_code == 200

    for methode, url in (('get', '/history/analyse-de-A/load'), ('get', f'/strategies/{sid}'),
                         ('get', '/export/pdf/analyse-de-A'), ('delete', '/history/analyse-de-A'),
                         ('delete', f'/strategies/{sid}')):
        r = getattr(b, methode)(url)
        # Une suppression sans effet peut répondre 200 : ce qui compte, c'est que rien ne soit effacé (vérifié plus bas).
        autorises = (200, 403, 404) if methode == 'delete' else (403, 404)
        assert r.status_code in autorises, f"B a obtenu {r.status_code} sur {methode.upper()} {url}"
        assert 'Secret de A' not in r.get_data(as_text=True) and 'secrète de A' not in r.get_data(as_text=True)

    # Les données de A sont intactes après les tentatives de B.
    assert a.get('/history/analyse-de-A/load').status_code == 200
    assert a.get(f'/strategies/{sid}').status_code == 200
    # Et la liste de B ne contient rien de A.
    corps = b.get('/history').get_data(as_text=True)
    assert 'analyse-de-A' not in corps and 'confidentielle' not in corps


def test_un_travail_en_cours_n_est_lisible_que_par_son_proprietaire(repli_local):
    import app as _app
    _app._jobs['job-prive-de-A'] = {'status': 'running', 'user_id': A, 'step': 'privé', 'progress': 40}
    try:
        assert _client_de(A).get('/api/v2/jobs/job-prive-de-A').get_json()['status'] == 'running'
        r = _client_de(B).get('/api/v2/jobs/job-prive-de-A')
        assert r.status_code == 404 and 'privé' not in r.get_data(as_text=True)
    finally:
        _app._jobs.pop('job-prive-de-A', None)


def test_sans_connexion_les_routes_de_donnees_repondent_401(repli_local):
    anonyme = _client_de(None)
    for url in ('/history', '/history/analyse-de-A/load', '/strategies/x', '/api/v2/jobs/x',
                '/api/v2/agents/psychologue/cross-analyses', '/api/v2/workspaces/x'):
        r = anonyme.get(url)
        assert r.status_code in (401, 302, 403), f"{url} répond {r.status_code} sans connexion"
        assert 'analyse-de-A' not in r.get_data(as_text=True)
    r = anonyme.post('/api/v2/agents/createur/generate', json={'content_type': 'youtube', 'user_request': 'x'})
    assert r.status_code == 401


# ── Mémoire stratégique : jamais les cas d'un autre compte ─────────────────

class _RequeteMemoire:
    def __init__(self, base): self.base, self.filtre = base, {}
    def select(self, *_): return self
    def order(self, *_a, **_k): return self
    def limit(self, *_): return self
    def eq(self, col, val): self.filtre[col] = val; return self
    def execute(self):
        self.base.requetes.append(dict(self.filtre))
        rows = [r for r in self.base.lignes if all(r.get(c) == v for c, v in self.filtre.items())]
        return type('R', (), {'data': rows})()


class _BaseMemoire:
    def __init__(self, lignes): self.lignes, self.requetes = lignes, []
    def table(self, _nom): return _RequeteMemoire(self)


PSYCHO_MEMOIRE = {
    'emotions': {'repartition': [{'emotion': 'frustration', 'pourcentage': 40}]},
    'psychologie': {'frustrations': ['peur de gaspiller du temps et de l’argent en matériel'],
                    'motivations_profondes': ['créer sans limites avec une IA locale']},
    'aspirations': {'ce_qu_ils_veulent_devenir': 'créateurs autonomes grâce à l’IA locale'},
}


def _cas(case_id, uid, offre):
    from core.memory import GabrielMemory
    return {'case_id': case_id, 'user_id': uid, 'case_date': '2026-09-01',
            'fingerprint': GabrielMemory(None)._fingerprint(PSYCHO_MEMOIRE, {}),     # identique : similarité maximale
            'audience': {'emotion_dominante': 'frustration', 'aspirations_resume': 'créer avec l’IA locale'},
            'strategie': {'decision_centrale': f'Décision de {uid}', 'offre_nom': offre, 'prix_recommande': '4 900 €'},
            'created_at': f'2026-09-0{case_id[-1]}'}


@pytest.fixture
def memoire(monkeypatch):
    base = _BaseMemoire([_cas('c1', A, 'Offre secrète de A'), _cas('c2', A, 'Autre offre de A'), _cas('c3', B, 'Offre de B')])
    monkeypatch.setattr(db, '_supabase', base)
    monkeypatch.delenv('MEMORY_SHARE_ACROSS_USERS', raising=False)
    return base


def test_la_memoire_ne_charge_que_les_cas_de_l_utilisateur(memoire):
    cas = db.get_memory_cases(B)
    assert [c['case_id'] for c in cas] == ['c3']
    assert all(requete.get('user_id') == B for requete in memoire.requetes), "une requête a lu les cas de tous les comptes"


def test_sans_utilisateur_aucun_cas_n_est_charge(memoire):
    assert db.get_memory_cases(None) == []
    assert memoire.requetes == []


def test_le_prompt_d_un_utilisateur_ne_contient_jamais_l_offre_d_un_autre(memoire):
    from core.memory import GabrielMemory
    contexte_b = GabrielMemory(B).get_memory_context(PSYCHO_MEMOIRE, {}, user_id=B)
    assert 'Décision de utilisateur-B' in contexte_b                         # sa propre mémoire fonctionne
    assert 'Offre secrète de A' not in contexte_b and 'Autre offre de A' not in contexte_b
    assert 'Décision de utilisateur-A' not in contexte_b


def test_le_partage_entre_comptes_reste_utilisable_quand_on_l_active(memoire, monkeypatch):
    from core.memory import GabrielMemory
    monkeypatch.setenv('MEMORY_SHARE_ACROSS_USERS', 'true')
    contexte_b = GabrielMemory(B).get_memory_context(PSYCHO_MEMOIRE, {}, user_id=B)
    assert 'Offre secrète de A' in contexte_b                                # comportement d'origine, sur demande


def test_le_partage_entre_comptes_reste_disponible_quand_on_l_active(memoire, monkeypatch):
    monkeypatch.setenv('MEMORY_SHARE_ACROSS_USERS', 'true')
    assert {c['case_id'] for c in db.get_memory_cases(B)} == {'c1', 'c2', 'c3'}


def test_meme_avec_un_pool_melange_la_recherche_de_cas_ne_rend_que_ceux_de_l_utilisateur(memoire, monkeypatch):
    """Seconde barrière : même si des cas d'autres comptes se retrouvaient en mémoire vive,
    find_similar ne les propose jamais (sauf partage explicitement activé)."""
    from core.memory import GabrielMemory, _row_to_case
    m = GabrielMemory(B)
    m.cases = [_row_to_case(r) for r in memoire.lignes]                       # A et B mélangés
    trouves = {i['case']['user_id'] for i in m.find_similar(PSYCHO_MEMOIRE, {}, user_id=B)}
    assert trouves == {B}
    monkeypatch.setenv('MEMORY_SHARE_ACROSS_USERS', 'true')
    assert A in {i['case']['user_id'] for i in m.find_similar(PSYCHO_MEMOIRE, {}, user_id=B)}
