"""Équivalence de l'outil de recherche documentaire.

Le modèle sémantique n'est pas chargé dans ces tests — trop lent, et non
hermétique (dépendrait du corpus réel). `core.rag.search` a déjà un chemin de
repli documenté quand le modèle est indisponible (ordre brut, score=1.0) :
c'est ce chemin, réellement emprunté en production si le modèle échoue à
charger, qui est exercé ici.
"""

import pytest

import tools as tools_pkg
from core import rag


AGENT_TEST = 'test_knowledge_tool'


@pytest.fixture
def index_factice(monkeypatch):
    """Un index en mémoire, sans passer par le disque ni le modèle."""
    chunks = [
        {'text': 'Le prix est le premier frein psychologique.', 'source': 'pricing'},
        {'text': 'La rareté perçue augmente la valeur ressentie.', 'source': 'pricing'},
        {'text': "L'audience cherche une transformation, pas un produit.", 'source': 'audience'},
    ]
    rag._indexes[AGENT_TEST] = {'chunks': chunks, 'embeddings': None, 'hash': 'x'}
    monkeypatch.setattr(rag, '_get_model', lambda: None)
    yield chunks
    rag._indexes.pop(AGENT_TEST, None)


class TestEquivalenceAvecLaChaineReelle:
    def test_loutil_rend_ce_que_search_et_format_context_rendent(self, index_factice):
        attendu_resultats = rag.search('prix', AGENT_TEST, top_k=2)
        attendu_contexte = rag.format_context(attendu_resultats)

        obtenu = tools_pkg.registry.get('knowledge.search').run(
            query='prix', agent=AGENT_TEST, top_k=2)

        assert obtenu['results'] == attendu_resultats
        assert obtenu['context'] == attendu_contexte

    def test_sources_fourni_bascule_reellement_sur_search_filtered(self, index_factice):
        attendu = rag.search_filtered('prix', AGENT_TEST, ['pricing'], top_k=5)
        obtenu = tools_pkg.registry.get('knowledge.search').run(
            query='prix', agent=AGENT_TEST, sources=['pricing'], top_k=5)
        assert obtenu['results'] == attendu
        assert all(r['source'] == 'pricing' for r in obtenu['results'])

    def test_sans_sources_le_corpus_entier_est_interroge(self, index_factice):
        obtenu = tools_pkg.registry.get('knowledge.search').run(
            query='audience', agent=AGENT_TEST, top_k=5)
        assert {r['source'] for r in obtenu['results']} == {'pricing', 'audience'}


class TestFormatage:
    def test_max_chars_est_reellement_transmis_au_formatage(self, index_factice):
        """Sans transmission réelle, une troncature demandée serait ignorée en
        silence — le prompt recevrait plus de texte que prévu."""
        large = tools_pkg.registry.get('knowledge.search').run(
            query='prix', agent=AGENT_TEST, top_k=5, max_chars=1800)
        court = tools_pkg.registry.get('knowledge.search').run(
            query='prix', agent=AGENT_TEST, top_k=5, max_chars=40)
        assert len(court['context']) < len(large['context'])
        assert len(court['context']) <= 40 + 20  # marge pour l'en-tête [source]


class TestCasLimites:
    def test_un_agent_sans_corpus_ne_leve_pas(self, monkeypatch):
        monkeypatch.setattr(rag, '_get_model', lambda: None)
        rag._indexes['corpus_vide'] = {'chunks': [], 'embeddings': None}
        try:
            obtenu = tools_pkg.registry.get('knowledge.search').run(
                query='x', agent='corpus_vide')
            assert obtenu == {'results': [], 'context': ''}
        finally:
            rag._indexes.pop('corpus_vide', None)

    def test_une_liste_de_sources_vide_se_comporte_comme_labsence_de_sources(self, index_factice):
        """`search_filtered` retombe elle-même sur une recherche globale sans
        source correspondante — vérifié ici : []  doit suivre le même chemin
        que `sources=None`, pas planter sur une liste vide."""
        avec_none = tools_pkg.registry.get('knowledge.search').run(
            query='prix', agent=AGENT_TEST, sources=None, top_k=5)
        avec_liste_vide = tools_pkg.registry.get('knowledge.search').run(
            query='prix', agent=AGENT_TEST, sources=[], top_k=5)
        assert avec_none['results'] == avec_liste_vide['results']


class TestContrat:
    def test_le_contrat_se_declare_pur_pour_un_index_stable(self):
        spec = tools_pkg.registry.get('knowledge.search').spec
        assert spec.deterministic is True
        assert spec.cacheable is True
        assert spec.parallel_safe is True
