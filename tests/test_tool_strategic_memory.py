"""Équivalence de l'outil de mémoire stratégique par similarité.

`GabrielMemory.find_similar` combine une lecture de cas (Supabase, via
`api.db.get_memory_cases`) et un score de similarité pur. La lecture est
simulée pour un test rapide et hermétique ; le score, lui, est le vrai
calcul de production — la preuve d'équivalence porte dessus.
"""

import core.memory as memory_module
import tools as tools_pkg
from core.memory import GabrielMemory


PSYCHO_DATA = {
    'emotions': {'repartition': [{'emotion': 'Espoir', 'pourcentage': 40}]},
    'aspirations': {'ce_qu_ils_veulent_devenir': 'entrepreneur libre et reconnu',
                    'transformation_visee': 'quitter le salariat'},
    'psychologie': {'frustrations': ['manque de temps', 'peur de se lancer'],
                    'motivations_profondes': ['liberté', 'reconnaissance']},
    'marketing': {'positionnement_recommande': 'Accompagnement premium'},
}
BUSINESS_CONTEXT = {'objectif_principal': 'lancer une offre premium'}


def _cas_stocke(case_id, user_id='u1'):
    """Un cas dont le fingerprint est calculé avec la vraie méthode — garantit
    un score de similarité réel, pas un chiffre inventé pour faire passer le
    test."""
    fingerprint = GabrielMemory()._fingerprint(PSYCHO_DATA, BUSINESS_CONTEXT)
    return {
        'case_id': case_id, 'user_id': user_id, 'date': '2026-01-01',
        'fingerprint': fingerprint,
        'audience': {}, 'strategie': {'decision_centrale': 'Offre premium à 490€'},
        'contexte_business': BUSINESS_CONTEXT, 'feedback': None,
        'satisfaction': None, 'performance': None,
    }


def _stub_cases(monkeypatch, cases):
    monkeypatch.setattr(memory_module._db, 'get_memory_cases', lambda uid: cases)


class TestEquivalenceAvecLaMethodeDOrigine:
    def test_loutil_rend_les_memes_correspondances_que_find_similar(self, monkeypatch):
        cas = [_cas_stocke('case_1')]
        _stub_cases(monkeypatch, cas)

        attendu = GabrielMemory('u1').find_similar(PSYCHO_DATA, BUSINESS_CONTEXT, user_id='u1')

        obtenu = tools_pkg.registry.get('strategic_memory.find_similar_cases').run(
            psycho_data=PSYCHO_DATA, business_context=BUSINESS_CONTEXT, user_id='u1')

        assert obtenu['matches'] == attendu
        assert obtenu['total_cases_considered'] == 1

    def test_un_cas_trop_different_nest_pas_retenu(self, monkeypatch):
        cas_different = {
            'case_id': 'c2', 'user_id': 'u1', 'date': '2026-01-01',
            'fingerprint': {
                'emotion_dominante': 'colere', 'asp_keywords': ['richesse'],
                'fru_keywords': ['administration'], 'motiv_keywords': ['securite'],
                'positionnement': 'discount', 'objectif_business': 'reduire les couts',
            },
            'audience': {}, 'strategie': {}, 'contexte_business': {},
            'feedback': None, 'satisfaction': None, 'performance': None,
        }
        _stub_cases(monkeypatch, [cas_different])
        obtenu = tools_pkg.registry.get('strategic_memory.find_similar_cases').run(
            psycho_data=PSYCHO_DATA, user_id='u1')
        assert obtenu['matches'] == []
        assert obtenu['total_cases_considered'] == 1

    def test_aucun_cas_ne_leve_pas(self, monkeypatch):
        _stub_cases(monkeypatch, [])
        obtenu = tools_pkg.registry.get('strategic_memory.find_similar_cases').run(
            psycho_data=PSYCHO_DATA)
        assert obtenu == {'matches': [], 'total_cases_considered': 0}


class TestPlusieursCorrespondances:
    def test_plusieurs_cas_similaires_sont_tous_rendus(self, monkeypatch):
        """Avec un seul cas en stock, une troncature silencieuse serait
        invisible — ce test l'expose avec deux cas similaires réels."""
        cas = [_cas_stocke('case_1'), _cas_stocke('case_2')]
        _stub_cases(monkeypatch, cas)

        attendu = GabrielMemory('u1').find_similar(PSYCHO_DATA, BUSINESS_CONTEXT, user_id='u1')
        obtenu = tools_pkg.registry.get('strategic_memory.find_similar_cases').run(
            psycho_data=PSYCHO_DATA, business_context=BUSINESS_CONTEXT, user_id='u1')

        assert len(attendu) == 2
        assert obtenu['matches'] == attendu


class TestContrat:
    def test_le_contrat_reconnait_la_dependance_reseau(self):
        """Contrairement aux calculs purement locaux : pas de cache silencieux
        sur des données qui changent entre deux appels."""
        spec = tools_pkg.registry.get('strategic_memory.find_similar_cases').spec
        assert spec.cacheable is False
        assert spec.parallel_safe is True
