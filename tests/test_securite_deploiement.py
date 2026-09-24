"""Un serveur déployé refuse de démarrer avec des réglages qui l'ouvriraient à tous."""
import os

os.environ.setdefault('FLASK_SECRET_KEY', 'test-secret-deploiement-suffisamment-long')
os.environ.setdefault('MISTRAL_API_KEY', 'test-key')

from app import production_safety_problems

SECRET_OK = 'x' * 40


def test_en_developpement_aucun_controle_ne_bloque_le_demarrage():
    assert production_safety_problems({'AUTH_ENABLED': 'false', 'FLASK_SECRET_KEY': 'court'}) == []
    # Le .env d'un poste de développement garde l'adresse publique : ce n'est pas un déploiement.
    assert production_safety_problems({'AUTH_ENABLED': 'false', 'APP_URL': 'https://gabriel.example.com', 'FLASK_SECRET_KEY': 'court'}) == []


def test_sur_render_l_authentification_est_obligatoire():
    problemes = production_safety_problems({'RENDER': 'true', 'FLASK_SECRET_KEY': SECRET_OK})           # variable oubliée
    assert len(problemes) == 1 and 'AUTH_ENABLED' in problemes[0]
    assert production_safety_problems({'RENDER': 'true', 'AUTH_ENABLED': 'false', 'FLASK_SECRET_KEY': SECRET_OK})
    assert production_safety_problems({'RENDER': 'true', 'AUTH_ENABLED': 'true', 'FLASK_SECRET_KEY': SECRET_OK}) == []


def test_gabriel_env_production_declare_aussi_un_deploiement():
    assert production_safety_problems({'GABRIEL_ENV': 'production', 'FLASK_SECRET_KEY': SECRET_OK})
    assert production_safety_problems({'GABRIEL_ENV': 'Production', 'AUTH_ENABLED': 'TRUE', 'FLASK_SECRET_KEY': SECRET_OK}) == []


def test_une_cle_secrete_faible_ou_d_exemple_est_refusee_en_deploiement():
    base = {'RENDER': '1', 'AUTH_ENABLED': 'true'}
    for faible in ('', 'court', 'VOTRE_CLE_SECRETE_ALEATOIRE_ICI'):
        problemes = production_safety_problems({**base, 'FLASK_SECRET_KEY': faible})
        assert any('FLASK_SECRET_KEY' in p for p in problemes), faible
    assert production_safety_problems({**base, 'FLASK_SECRET_KEY': SECRET_OK}) == []


def _importer_app(env_supplementaire):
    """Importe vraiment l'application dans un processus neuf, comme le ferait gunicorn."""
    import subprocess
    import sys
    env = {k: v for k, v in os.environ.items() if k not in ('RENDER', 'GABRIEL_ENV', 'AUTH_ENABLED', 'APP_URL')}
    env.update({'NLP_PRELOAD': 'false', 'JOB_SWEEP_ON_START': '0', 'SUPABASE_URL': '', 'SUPABASE_KEY': '',
                'FLASK_SECRET_KEY': SECRET_OK, 'MISTRAL_API_KEY': 'test-key', **env_supplementaire})
    racine = os.path.dirname(os.path.dirname(__file__))
    return subprocess.run([sys.executable, '-c', 'import app'], cwd=racine, env=env, capture_output=True, text=True, timeout=120)


def test_le_serveur_deploye_sans_authentification_refuse_reellement_de_demarrer():
    # AUTH_ENABLED explicitement à false : sinon le .env local du poste de développement le fournirait.
    r = _importer_app({'RENDER': 'true', 'AUTH_ENABLED': 'false'})
    assert r.returncode != 0 and 'Démarrage refusé' in r.stderr and 'AUTH_ENABLED' in r.stderr


def test_le_serveur_deploye_correctement_configure_demarre():
    r = _importer_app({'RENDER': 'true', 'AUTH_ENABLED': 'true'})
    assert r.returncode == 0, r.stderr[-500:]
