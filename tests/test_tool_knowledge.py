"""Équivalence de l'outil de recherche documentaire, sans modèle distant."""

import pytest
import numpy as np

import tools as tools_pkg
from core import rag


AGENT_TEST = 'test_knowledge_tool'


@pytest.fixture
def index_factice(monkeypatch):
    """Un index et un encodeur déterministes, entièrement en mémoire."""
    chunks = [
        {'text': 'Le prix est le premier frein psychologique.', 'source': 'pricing'},
        {'text': 'La rareté perçue augmente la valeur ressentie.', 'source': 'pricing'},
        {'text': "L'audience cherche une transformation, pas un produit.", 'source': 'audience'},
    ]

    class FakeSemanticModel:
        def encode(self, texts, **_kwargs):
            return np.asarray([
                [1.0, 0.0] if 'prix' in text.lower() else [0.0, 1.0]
                for text in texts
            ])

    rag._indexes[AGENT_TEST] = {
        'chunks': chunks,
        'embeddings': np.asarray([[1.0, 0.0], [0.8, 0.2], [0.0, 1.0]]),
        'hash': 'x',
    }
    monkeypatch.setattr(rag, '_get_model', lambda: FakeSemanticModel())
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

    def test_un_index_sans_embeddings_echoue_explicitement(self, monkeypatch):
        rag._indexes['index_incomplet'] = {
            'chunks': [{'text': 'contenu', 'source': 'test'}],
            'embeddings': None,
            'hash': 'x',
        }
        monkeypatch.setattr(rag, '_get_model', lambda: None)
        try:
            with pytest.raises(rag.RAGEmbeddingUnavailableError, match='embeddings'):
                tools_pkg.registry.get('knowledge.search').run(
                    query='contenu', agent='index_incomplet')
        finally:
            rag._indexes.pop('index_incomplet', None)


class TestContrat:
    def test_le_contrat_se_declare_pur_pour_un_index_stable(self):
        spec = tools_pkg.registry.get('knowledge.search').spec
        assert spec.deterministic is True
        assert spec.cacheable is True
        assert spec.parallel_safe is True


class TestCartesDeConcept:
    """Chaîne à trois fonctions (charger → filtrer par signaux → formater),
    appelée deux fois à l'identique dans le pipeline du Psychologue — pour la
    psychologie puis pour le socioculturel. L'outil déclare la chaîne réelle.
    """

    # Signaux réalistes : le pipeline envoie émotion dominante, posture, titre,
    # puis d'éventuels marqueurs. Les déclencheurs des cartes sont des phrases
    # entières, donc un signal ne pèse que s'il y apparaît réellement — des
    # mots choisis au hasard ne discriminent rien, et c'est correct.
    SIGNAUX = ['Espoir', 'favorable', 'frustration élevée']

    def test_loutil_rend_ce_que_la_chaine_reelle_rend(self):
        cards = rag.load_concept_cards('psychologie')
        attendu_cards = rag.filter_concept_cards_by_triggers(
            cards, self.SIGNAUX, max_cards=4)
        attendu_ctx = rag.format_concept_cards_context(attendu_cards, max_chars=1500)

        obtenu = tools_pkg.registry.get('knowledge.concept_cards').run(
            rag_name='psychologie', dashboard_signals=self.SIGNAUX,
            max_cards=4, max_chars=1500)

        assert obtenu['cards'] == attendu_cards
        assert obtenu['context'] == attendu_ctx

    def test_le_corpus_reel_est_bien_charge(self):
        obtenu = tools_pkg.registry.get('knowledge.concept_cards').run(
            rag_name='psychologie')
        assert obtenu['available'] == 12
        assert len(obtenu['cards']) == 4          # plafond par défaut
        assert all('id' in c for c in obtenu['cards'])

    def test_les_signaux_changent_reellement_la_selection(self):
        """Sans cet effet, l'outil rendrait toujours les mêmes cartes et le
        filtrage par signaux ne servirait à rien. Les signaux employés ici
        figurent réellement dans les déclencheurs des cartes — vérifié."""
        outil = tools_pkg.registry.get('knowledge.concept_cards')
        tension = outil.run(rag_name='psychologie',
                           dashboard_signals=['tension_interne'])
        croyances = outil.run(rag_name='psychologie',
                             dashboard_signals=['croyances_limitantes'])
        assert [c['id'] for c in tension['cards']][0] == 'PSY-001'
        assert [c['id'] for c in croyances['cards']][0] == 'PSY-007'

    def test_un_signal_absent_des_declencheurs_laisse_l_ordre_inchange(self):
        """Comportement d'origine, à ne pas confondre avec une panne : un mot
        qui ne figure dans aucun déclencheur ne réordonne rien. Le tri est
        stable, donc l'ordre du corpus est conservé."""
        outil = tools_pkg.registry.get('knowledge.concept_cards')
        sans_signal = outil.run(rag_name='psychologie', dashboard_signals=[])
        mot_absent = outil.run(rag_name='psychologie',
                              dashboard_signals=['xyzzy_inexistant'])
        assert [c['id'] for c in sans_signal['cards']] == \
            [c['id'] for c in mot_absent['cards']]

    def test_sans_signaux_les_premieres_cartes_sont_rendues(self):
        """Comportement d'origine : pas de signaux, pas de tri — on ne fabrique
        pas une pertinence qu'on n'a pas."""
        obtenu = tools_pkg.registry.get('knowledge.concept_cards').run(
            rag_name='psychologie', dashboard_signals=[], max_cards=2)
        attendu = rag.load_concept_cards('psychologie')[:2]
        assert obtenu['cards'] == attendu

    def test_un_corpus_inexistant_ne_leve_pas(self):
        obtenu = tools_pkg.registry.get('knowledge.concept_cards').run(
            rag_name='corpus_qui_nexiste_pas')
        assert obtenu == {'cards': [], 'context': '', 'available': 0}

    def test_le_contrat_se_declare_pur(self):
        spec = tools_pkg.registry.get('knowledge.concept_cards').spec
        assert spec.deterministic is True and spec.cacheable is True
