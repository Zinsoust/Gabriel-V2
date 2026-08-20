"""Contrat du registre de mémoires.

Cinq types de mémoire existent déjà dans Gabriel, chacun dans son propre
mécanisme de stockage, sans qu'aucun endroit ne les déclare ensemble. Ce
registre répond à « quelle mémoire Gabriel a-t-il, et d'où vient-elle ? »
sans réécrire aucun stockage — il référence les fonctions d'accès existantes.
"""

import pytest

from core.memory_manager import (STATUS_AVAILABLE, STATUS_PLANNED,
                                 MemoryEntry, MemoryError, MemoryNotFound,
                                 MemoryRegistry, MemorySpec, MemoryUnavailable)
import core.memories as memories
from core.memory_manager import registry


class TestHonneteteSurCeQuiEstBranche:
    """Trois des cinq mémoires vivent dans app.py, qui n'est importé par aucun
    autre module — l'y importer créerait une dépendance qui n'existe nulle
    part ailleurs. Le registre le dit plutôt que de le cacher."""

    def test_deux_memoires_sont_reellement_branchees(self):
        assert {'conversation', 'strategic'} == {
            m.spec.id for m in registry.available()}

    def test_trois_memoires_sont_declarees_sans_etre_lisibles(self):
        for memory_id in ('user', 'business', 'audience'):
            assert memory_id in registry
            assert registry.get(memory_id).spec.usable is False

    def test_lire_une_memoire_non_branchee_echoue_explicitement(self):
        with pytest.raises(MemoryUnavailable, match='app.py'):
            registry.fetch('business', data={}, uid='u1')

    def test_chaque_memoire_declaree_dit_ou_vit_son_vrai_mecanisme(self):
        """Traçabilité : une mémoire déclarée doit pouvoir être retrouvée."""
        for entry in registry.all():
            assert entry.spec.source, entry.spec.id


class TestLectureDesMemoiresBranchees:
    def test_lire_la_memoire_conversationnelle_sans_historique(self):
        resultat = registry.fetch('conversation', previous={},
                                  message="On vend un abonnement à 49€/mois.")
        assert resultat.spec_id == 'conversation'
        assert resultat.empty is False
        assert resultat.content['facts'].get('offre')

    def test_lire_la_memoire_strategique_sans_cas_connu(self):
        resultat = registry.fetch('strategic', psycho_data={}, user_id='inexistant')
        assert resultat.empty is True
        assert resultat.content == ''

    def test_une_lecture_sans_les_cles_requises_echoue(self):
        with pytest.raises(MemoryError, match='message'):
            registry.fetch('conversation', previous={})


class TestProvenance:
    """La mémoire business retombe aujourd'hui en silence sur trois sources
    sans jamais dire laquelle a répondu — la provenance corrige cela pour les
    mémoires déjà branchées."""

    def test_chaque_lecture_declare_sa_provenance(self):
        resultat = registry.fetch('conversation', previous={}, message='bonjour')
        assert resultat.provenance == 'in_memory_blob'
        resultat = registry.fetch('strategic', psycho_data={})
        assert resultat.provenance == 'supabase_case_memory'


class TestEquivalenceAvecLesFonctionsDOrigine:
    """Le registre ne réécrit rien : il référence. La comparaison ne porte pas
    sur ce que le registre produit lui-même mais sur l'appel direct de la
    fonction d'origine, pour que le passage par le registre ne change rien."""

    def test_la_lecture_conversationnelle_rend_ce_que_la_fonction_rend(self):
        from agents.orchestrator.conversation_memory import update_conversation_memory

        message = "On vend un abonnement à 49€/mois pour les coachs."
        attendu = update_conversation_memory({}, message)
        obtenu = registry.fetch('conversation', previous={}, message=message)
        assert obtenu.content == attendu

    def test_la_lecture_strategique_rend_ce_que_GabrielMemory_rend(self):
        from core.memory import GabrielMemory

        attendu = GabrielMemory('inconnu').get_memory_context({}, user_id='inconnu')
        obtenu = registry.fetch('strategic', psycho_data={}, user_id='inconnu')
        assert obtenu.content == attendu


class TestRegistre:
    def test_un_identifiant_en_double_est_refuse(self):
        r = MemoryRegistry()
        spec = MemorySpec(id='x', name='X', description='…', scope='global')
        r.register(spec)
        with pytest.raises(ValueError, match='déjà enregistrée'):
            r.register(spec)

    def test_une_memoire_inconnue_liste_les_memoires_declarees(self):
        with pytest.raises(MemoryNotFound, match='conversation'):
            registry.get('conversation-absente')

    def test_un_statut_invalide_est_refuse(self):
        with pytest.raises(ValueError, match='Statut invalide'):
            MemorySpec(id='x', name='X', description='…', scope='global',
                      status='peut-etre')

    def test_le_registre_distingue_declarees_et_branchees(self):
        assert len(registry) == 5
        assert len(registry.available()) == 2
