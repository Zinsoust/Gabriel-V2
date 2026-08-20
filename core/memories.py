"""Déclaration des cinq mémoires de Gabriel.

Les cinq sont désormais branchées. ``user``, ``business`` et ``audience``
vivaient dans ``app.py`` — inatteignable pour ce module (voir la note
historique dans ``core/memory_manager.py``) — et ont été extraites vers
``core/business_context.py`` sans changement de comportement, le même geste
déjà fait pour les outils du Psychologue et les savoir-faire du Créateur.
"""

from core.memory_manager import STATUS_AVAILABLE, MemoryEntry, MemorySpec, registry


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

def _fetch_user(*, uid) -> MemoryEntry:
    from core.business_context import get_user_profile
    profil = get_user_profile(uid)
    return MemoryEntry('user', profil, not bool(profil), provenance='profile_file')


def _fetch_business(*, data, uid) -> MemoryEntry:
    from core.business_context import resolve_business_context
    contexte = resolve_business_context(data, uid)
    # La cascade retombe en silence sur trois sources : la déclarer ici évite
    # qu'un appelant confonde un profil frais avec un legacy oublié.
    if data.get('business_context'):
        provenance = 'request_body'
    elif uid:
        provenance = 'context_builder_interview_or_legacy_profile'
    else:
        provenance = 'none'
    return MemoryEntry('business', contexte, not bool(contexte), provenance=provenance)


def _fetch_audience(*, folder_id, user_id, include_agents=()) -> MemoryEntry:
    from core.business_context import load_workspace_context
    contenu = load_workspace_context(folder_id, user_id, include_agents)
    return MemoryEntry('audience', contenu, not bool(contenu.get('loaded_agents')),
                       provenance='workspace_reports')


USER_MEMORY = MemorySpec(
    id='user',
    name='Profil utilisateur (hérité)',
    description="Profil business par fichier, mécanisme antérieur à l'Entretien stratégique.",
    scope='user',
    required_keys=('uid',),
    status=STATUS_AVAILABLE,
    source='core/business_context.py::get_user_profile',
)

BUSINESS_MEMORY = MemorySpec(
    id='business',
    name='Contexte business',
    description=(
        "Contexte business résolu par cascade : requête, puis Entretien "
        "stratégique (Supabase), puis profil hérité en dernier recours."),
    scope='user',
    required_keys=('data', 'uid'),
    status=STATUS_AVAILABLE,
    source='core/business_context.py::resolve_business_context',
)

AUDIENCE_MEMORY = MemorySpec(
    id='audience',
    name="Rapports d'agents (workspace)",
    description=(
        "Rapports du Psychologue, du Stratège et du Créateur pour un "
        "workspace, chargés seulement quand la conversation les appelle."),
    scope='session',
    required_keys=('folder_id', 'user_id'),
    status=STATUS_AVAILABLE,
    source='core/business_context.py::load_workspace_context',
)


def register_all() -> None:
    registry.register(CONVERSATION_MEMORY, _fetch_conversation)
    registry.register(STRATEGIC_MEMORY, _fetch_strategic)
    registry.register(USER_MEMORY, _fetch_user)
    registry.register(BUSINESS_MEMORY, _fetch_business)
    registry.register(AUDIENCE_MEMORY, _fetch_audience)


register_all()
