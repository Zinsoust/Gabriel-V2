"""Extraction Utilisateur / Business / Audience hors de app.py.

Ces trois fonctions vivaient dans app.py, la feuille de l'arbre d'imports —
inatteignable pour tout autre module. Elles sont ici, dans un module que
core/memories.py peut réellement importer, sans changement de comportement.
"""

import json

import pytest

import core.business_context as bc


class TestModuleIndependantDApp:
    """La preuve de l'extraction : aucun import statique de core.business_context
    ne remonte vers app.py. Un test sur sys.modules serait ici trompeur — la
    suite complète charge d'autres fichiers de test qui importent `app` pour
    leur client Flask, ce qui pollue l'état global sans rapport avec ce module."""

    def test_aucun_module_de_production_n_importe_app(self):
        """Contrainte vérifiée avant l'extraction, à ne jamais régresser :
        app.py doit rester une feuille, jamais une racine. Les tests qui
        importent `app` pour un client Flask de test sont légitimes et exclus."""
        import pathlib
        racine = pathlib.Path(__file__).resolve().parent.parent
        ignores = {'.git', 'venv', '.venv', 'tests', 'node_modules'}
        hors_tests = [
            str(path)
            for path in racine.rglob('*.py')
            if not ignores.intersection(path.relative_to(racine).parts)
            and 'from app import' in path.read_text(encoding='utf-8')
        ]
        assert hors_tests == []


class TestMemoireUtilisateur:
    def test_un_profil_absent_rend_un_dict_vide(self, tmp_path, monkeypatch):
        monkeypatch.setattr(bc, '_PROFILES_DIR', str(tmp_path))
        monkeypatch.setattr(bc, '_BRAIN_FILE', str(tmp_path / 'absent.json'))
        assert bc.get_user_profile('inconnu') == {}

    def test_sauvegarder_puis_lire_rend_le_meme_profil(self, tmp_path, monkeypatch):
        monkeypatch.setattr(bc, '_PROFILES_DIR', str(tmp_path))
        monkeypatch.setattr(bc, '_BRAIN_FILE', str(tmp_path / 'legacy.json'))
        profil = {'activite': 'Coaching', 'offre': 'Programme 12 semaines'}
        bc.save_user_profile('u1', profil)
        assert bc.get_user_profile('u1') == profil

    def test_un_profil_illisible_ne_fait_pas_planter_la_lecture(self, tmp_path, monkeypatch):
        """Comportement historique : un fichier corrompu ne doit pas faire
        tomber la page qui affiche le profil."""
        monkeypatch.setattr(bc, '_PROFILES_DIR', str(tmp_path))
        monkeypatch.setattr(bc, '_BRAIN_FILE', str(tmp_path / 'legacy.json'))
        (tmp_path / 'u2.json').write_text('{ pas du json')
        assert bc.get_user_profile('u2') == {}


class TestNormalisationDeProfil:
    def test_les_clefs_de_l_entretien_deviennent_des_clefs_brain(self):
        assert bc.normalize_profile({'activity': 'Coaching', 'priority_offer': 'X'}) == {
            'activite': 'Coaching', 'offre': 'X'}

    def test_une_clef_inconnue_traverse_sans_modification(self):
        assert bc.normalize_profile({'champ_libre': 'v'}) == {'champ_libre': 'v'}

    def test_un_profil_vide_rend_un_dict_vide(self):
        assert bc.normalize_profile({}) == {} and bc.normalize_profile(None) == {}


class TestMemoireBusiness:
    def test_le_corps_de_la_requete_est_prioritaire(self, monkeypatch):
        monkeypatch.setattr(bc, 'get_user_profile', lambda uid: {'activite': 'jamais lu'})
        resultat = bc.resolve_business_context(
            {'business_context': {'activity': 'Coaching'}}, 'u1')
        assert resultat == {'activite': 'Coaching'}

    def test_a_defaut_l_entretien_stratifique_prend_le_relai(self, monkeypatch):
        monkeypatch.setattr(bc._db, 'get_context_fields',
                            lambda uid: {'activity': 'Menuiserie'})
        monkeypatch.setattr(bc, 'get_user_profile', lambda uid: {'activite': 'jamais lu'})
        resultat = bc.resolve_business_context({}, 'u1')
        assert resultat == {'activite': 'Menuiserie'}

    def test_le_profil_herite_est_le_dernier_recours(self, monkeypatch):
        """C'est le défaut trouvé en conditions réelles : sans ce dernier
        recours documenté, un compte jamais passé par l'entretien se
        retrouvait avec un Créateur qui écrit sans aucun contexte."""
        monkeypatch.setattr(bc._db, 'get_context_fields', lambda uid: {})
        monkeypatch.setattr(bc, 'get_user_profile', lambda uid: {'activite': 'Plomberie'})
        assert bc.resolve_business_context({}, 'u1') == {'activite': 'Plomberie'}

    def test_sans_utilisateur_l_entretien_n_est_jamais_interroge(self, monkeypatch):
        appels = []
        monkeypatch.setattr(bc._db, 'get_context_fields', lambda uid: appels.append(uid) or {})
        monkeypatch.setattr(bc, 'get_user_profile', lambda uid: {})
        bc.resolve_business_context({}, None)
        assert appels == []


class TestMemoireAudience:
    def _stub_db(self, monkeypatch, folder, analysis=None, strategy=None, job=None):
        monkeypatch.setattr(bc._db, 'get_folder_by_id', lambda fid, uid: folder)
        monkeypatch.setattr(bc._db, 'get_analysis_by_id', lambda aid, uid: analysis)
        monkeypatch.setattr(bc._db, 'get_strategy_by_id', lambda sid, uid: strategy)
        monkeypatch.setattr(bc._db, 'get_job', lambda jid, user_id=None: job)

    def test_sans_workspace_rien_n_est_charge(self, monkeypatch):
        self._stub_db(monkeypatch, folder=None)
        etat = bc.load_workspace_context('f1', 'u1', include_agents=('psychologue',))
        assert etat['psycho_data'] == {} and etat['loaded_agents'] == []

    def test_seul_l_agent_demande_est_lu_meme_si_disponible(self, monkeypatch):
        """Le contenu complet n'est relu que si le plan de conversation
        l'autorise — sans quoi chaque message rechargerait tous les rapports."""
        self._stub_db(monkeypatch,
                      folder={'analysis_id': 'a1', 'strategy_id': 's1'},
                      analysis={'full_result': {'x': 1}},
                      strategy={'strategy_result': {'y': 2}})
        etat = bc.load_workspace_context('f1', 'u1', include_agents=('psychologue',))
        assert etat['psycho_data'] == {'x': 1}
        assert etat['strategy_data'] == {}          # disponible, mais pas demandé
        assert etat['availability']['stratege'] is True  # la disponibilité, elle, est vraie
        assert etat['loaded_agents'] == ['psychologue']

    def test_psychologue_n_est_pas_charge_s_il_n_est_pas_demande(self, monkeypatch):
        """Symétrique au test ci-dessus, côté Psychologue : la présence d'un
        analysis_id ne doit jamais suffire à en relire le contenu."""
        self._stub_db(monkeypatch, folder={'analysis_id': 'a1'},
                      analysis={'full_result': {'x': 1}})
        etat = bc.load_workspace_context('f1', 'u1', include_agents=('stratege',))
        assert etat['psycho_data'] == {}
        assert etat['availability']['psychologue'] is True
        assert etat['loaded_agents'] == []

    def test_un_rapport_d_un_autre_workspace_est_ignore(self, monkeypatch):
        """Un résultat n'est lisible que depuis le workspace qui le référence —
        sans ce filtre, un lien d'analyse partagé fuiterait entre workspaces."""
        self._stub_db(monkeypatch,
                      folder={'analysis_id': 'a1'},
                      analysis={'full_result': {'x': 1}, 'folder_id': 'AUTRE'})
        etat = bc.load_workspace_context('f1', 'u1', include_agents=('psychologue',))
        assert etat['psycho_data'] == {}

    def test_les_jobs_crea_anciens_stockent_le_contenu_directement(self, monkeypatch):
        self._stub_db(monkeypatch, folder={'creator_output_id': 'j1'},
                      job={'result_data': {'texte': 'bonjour'}})
        etat = bc.load_workspace_context('f1', 'u1', include_agents=('createur',))
        assert etat['createur_data'] == {'texte': 'bonjour'}
