"""Déclaration des cinq mémoires de Gabriel.

``conversation`` et ``strategic`` sont branchées : leurs fonctions d'accès
vivent dans des modules importables et sont référencées telles quelles.

``user``, ``business`` et ``audience`` vivent aujourd'hui dans ``app.py`` —
voir la note dans ``core/memory_manager.py``. Elles sont déclarées
``STATUS_PLANNED`` : visibles dans le catalogue, honnêtes sur leur statut,
prêtes à être branchées le jour où leurs fonctions d'accès seront extraites.
"""

from core.memory_manager import (STATUS_AVAILABLE, STATUS_PLANNED,
                                 MemoryEntry, MemorySpec, registry)


def _fetch_conversation(*, previous: dict, message: str, history=(),
                        folder=None, available_agents=()) -> MemoryEntry:
    from agents.orchestrator.conversation_memory import update_conversation_memory
    contenu = update_conversation_memory(previous, message, history, folder,
                                         available_agents)
    vide = not contenu.get('facts') and not contenu.get('topics')
    return MemoryEntry('conversation', contenu, vide, provenance='in_memory_blob')


def _fetch_strategic(*, psycho_data: dict, business_context=None,
                     user_id=None) -> MemoryEntry:
    from core.memory import GabrielMemory
    contexte = GabrielMemory(user_id).get_memory_context(
        psycho_data, business_context, user_id=user_id)
    return MemoryEntry('strategic', contexte, not bool(contexte),
                       provenance='supabase_case_memory')


CONVERSATION_MEMORY = MemorySpec(
    id='conversation',
    name='Mémoire conversationnelle',
    description=(
        "Faits business explicitement formulés par l'utilisateur au fil de "
        "la discussion (offre, cible, objectif, contrainte), pour ne pas "
        "perdre le sujet après plusieurs tours."),
    scope='conversation',
    required_keys=('previous', 'message'),
    status=STATUS_AVAILABLE,
    source='agents/orchestrator/conversation_memory.py',
)

STRATEGIC_MEMORY = MemorySpec(
    id='strategic',
    name='Mémoire stratégique',
    description=(
        "Cas passés (fingerprint audience + stratégie + feedback) utilisés "
        "pour éclairer une nouvelle décision par similarité."),
    scope='global',
    required_keys=('psycho_data',),
    status=STATUS_AVAILABLE,
    source='core/memory.py::GabrielMemory',
)

USER_MEMORY = MemorySpec(
    id='user',
    name='Profil utilisateur (hérité)',
    description="Profil business par fichier, mécanisme antérieur à l'Entretien stratégique.",
    scope='user',
    required_keys=('uid',),
    status=STATUS_PLANNED,
    source='app.py::_get_user_profile',
)

BUSINESS_MEMORY = MemorySpec(
    id='business',
    name='Contexte business',
    description=(
        "Contexte business résolu par cascade : requête, puis Entretien "
        "stratégique (Supabase), puis profil hérité en dernier recours."),
    scope='user',
    required_keys=('data', 'uid'),
    status=STATUS_PLANNED,
    source='app.py::_resolve_business_context',
)

AUDIENCE_MEMORY = MemorySpec(
    id='audience',
    name='Rapports d\'agents (workspace)',
    description=(
        "Rapports du Psychologue, du Stratège et du Créateur pour un "
        "workspace, chargés seulement quand la conversation les appelle."),
    scope='session',
    required_keys=('folder_id', 'user_id'),
    status=STATUS_PLANNED,
    source='app.py::_orchestrator_load_context',
)


def register_all() -> None:
    registry.register(CONVERSATION_MEMORY, _fetch_conversation)
    registry.register(STRATEGIC_MEMORY, _fetch_strategic)
    registry.register(USER_MEMORY)
    registry.register(BUSINESS_MEMORY)
    registry.register(AUDIENCE_MEMORY)


register_all()
