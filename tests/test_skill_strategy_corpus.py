"""Corpus stratégique — 39 méthodes business nommées, rendues énumérables.

Ce Skill diffère des précédents : son contenu n'est pas choisi par clé mais
récupéré par pertinence. La preuve attendue n'est donc pas « bonne variante
choisie » mais « les 39 méthodes du corpus sont réellement déclarées, et la
récupération passe bien par l'outil documentaire ».
"""

import json
import pathlib

import pytest

import skills
from skills.base import CorpusSkill, SkillSpec
from skills.strategy_corpus import _load_corpus_entries


CORPUS_DIR = pathlib.Path(__file__).resolve().parent.parent / 'agents' / 'stratege' / 'rag'


def _ids_reels_du_corpus():
    """Relit les identifiants directement depuis les fichiers, sans passer par
    le chargeur du Skill — sinon la comparaison serait tautologique."""
    ids = set()
    for path in sorted(CORPUS_DIR.rglob('*.json')):
        if path.name == 'router_rules.json':
            continue
        data = json.loads(path.read_text(encoding='utf-8'))
        if isinstance(data, list):
            ids.update(str(item['id']) for item in data
                      if isinstance(item, dict) and item.get('id'))
    return ids


class TestEnumerabiliteDuCorpus:
    """Ce que la recherche sémantique seule ne donne pas : pouvoir demander
    « quelles méthodes Gabriel connaît-il ? » sans deviner les bons mots."""

    def test_les_39_methodes_du_corpus_sont_declarees(self):
        assert set(skills.registry.get('strategy.business_corpus').keys()) == \
            _ids_reels_du_corpus()

    def test_le_corpus_compte_bien_39_methodes(self):
        assert len(skills.registry.get('strategy.business_corpus').keys()) == 39

    def test_covers_repond_avant_de_promettre_une_methode(self):
        skill = skills.registry.get('strategy.business_corpus')
        assert skill.covers('value_based_pricing') is True
        assert skill.covers('methode_inventee') is False

    def test_chaque_methode_porte_un_libelle_lisible(self):
        """Les entrées n'ont pas toutes le même champ descriptif — `principle`
        pour les méthodes, `pattern` pour les schémas de marché. Aucune ne doit
        se retrouver sans libellé."""
        entries = skills.registry.get('strategy.business_corpus').describe()['entries']
        assert all(str(label).strip() for label in entries.values())
        assert entries['value_based_pricing'].startswith('Le prix juste')
        assert entries['selling_to_everyone'] == 'Vendre à tout le monde'


class TestLecteurDeCorpusFidele:
    def test_le_chargeur_ne_confond_pas_la_configuration_avec_une_methode(self, tmp_path,
                                                                          monkeypatch):
        """`router_rules.json` est de la configuration de recherche, pas une
        méthode — l'inclure gonflerait le catalogue d'une fausse capacité.

        Le fichier réel est un objet, donc déjà écarté par le filtre de forme.
        On l'écrit ici sous forme de liste pour exercer réellement la garde par
        nom de fichier — sinon ce test passerait sans rien protéger."""
        import skills.strategy_corpus as corpus_module
        (tmp_path / 'router_rules.json').write_text(
            '[{"id": "rag_name", "principle": "configuration, pas une méthode"}]',
            encoding='utf-8')
        (tmp_path / 'vraie_methode.json').write_text(
            '[{"id": "methode_valide", "principle": "Un principe"}]', encoding='utf-8')
        monkeypatch.setattr(corpus_module, '_CORPUS_DIR', tmp_path)

        entries = corpus_module._load_corpus_entries()
        assert entries == {'methode_valide': 'Un principe'}

    def test_le_corpus_reel_ne_contient_aucune_cle_de_configuration(self):
        assert 'rag_name' not in _load_corpus_entries()

    def test_un_fichier_illisible_ne_fait_pas_disparaitre_les_autres(self, tmp_path,
                                                                    monkeypatch):
        import skills.strategy_corpus as corpus_module
        (tmp_path / 'bon.json').write_text(
            '[{"id": "methode_valide", "principle": "Un principe"}]', encoding='utf-8')
        (tmp_path / 'casse.json').write_text('{ pas du json', encoding='utf-8')
        monkeypatch.setattr(corpus_module, '_CORPUS_DIR', tmp_path)
        assert corpus_module._load_corpus_entries() == {'methode_valide': 'Un principe'}


class TestRecuperationParPertinence:
    def test_la_recuperation_passe_par_loutil_documentaire(self, monkeypatch):
        """Un Skill enseigne, il n'exécute pas : la recherche est le travail
        d'un Tool déjà déclaré, pas une réimplémentation locale."""
        import skills.strategy_corpus as corpus_module
        appels = []

        def _faux_registre_outils():
            class _Outil:
                def run(self, **kwargs):
                    appels.append(kwargs)
                    return {'context': 'MÉTHODES PERTINENTES', 'results': []}

            class _Registre:
                def get(self, tool_id):
                    appels.append({'tool_id': tool_id})
                    return _Outil()
            return _Registre()

        monkeypatch.setattr(corpus_module, '_retrieve',
                            lambda q: _faux_registre_outils().get(
                                'knowledge.search').run(query=q, agent='stratege'))
        skill = corpus_module._corpus_skill()
        fragment = skill.render('Quel prix pour une offre premium ?')

        assert appels[0]['tool_id'] == 'knowledge.search'
        assert fragment.content['context'] == 'MÉTHODES PERTINENTES'

    def test_le_skill_declare_loutil_quil_mobilise(self):
        """Première utilisation réelle du champ `allowed_tools` de SkillSpec."""
        spec = skills.registry.get('strategy.business_corpus').spec
        assert spec.allowed_tools == ('knowledge.search',)


class TestHonneteteDuFragment:
    def _skill_avec_retrieve(self, retour):
        return CorpusSkill(
            spec=SkillSpec(id='test.corpus', name='T', description='…',
                          domain='test'),
            entries={'methode_a': 'Un principe'},
            retrieve=lambda q: retour)

    def test_un_corpus_indisponible_ne_se_fait_pas_passer_pour_un_silence(self):
        """Rendre un fragment vide sans le dire serait indiscernable d'un Skill
        qui n'a rien à ajouter — le même défaut que la couche Skill corrige
        depuis le début."""
        fragment = self._skill_avec_retrieve('').render('une situation')
        assert fragment.origin == 'none' and fragment.empty is True

    def test_une_demande_vide_ne_declenche_aucune_recuperation(self):
        appels = []
        skill = CorpusSkill(
            spec=SkillSpec(id='test.corpus', name='T', description='…', domain='test'),
            entries={}, retrieve=lambda q: appels.append(q) or 'x')
        skill.render('')
        assert appels == []

    def test_un_contenu_recupere_est_marque_comme_venant_du_corpus(self):
        skill = CorpusSkill(
            spec=SkillSpec(id='test.corpus', name='T', description='…', domain='test'),
            entries={'methode_a': 'Un principe'},
            retrieve=lambda q: 'CONTENU')
        fragment = skill.render('une situation')
        assert fragment.origin == 'corpus'
        assert fragment.content == 'CONTENU'
        # `known` reste faux : rien n'a été « choisi » au catalogue.
        assert fragment.known is False


class TestFicheASeptChamps:
    def test_les_six_champs_textuels_sont_renseignes(self):
        assert skills.registry.get('strategy.business_corpus').spec.is_fully_documented()

    def test_la_fiche_dit_ce_qui_nest_pas_rebranche(self):
        """Le routage par catégorie de production est plus riche que cette
        recherche unique — le taire laisserait croire à une équivalence."""
        limitations = skills.registry.get('strategy.business_corpus').spec.limitations
        assert '_load_rag_rules' in limitations
