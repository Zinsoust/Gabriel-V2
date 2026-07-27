# ═══════════════════════════════════════════════════════════════════════════
# CONTEXT BUILDER ARCHITECTURE — Orchestrator (V1.1)
#
# Chef d'orchestre : pilote schema / store / question_planner /
# answer_extractor / tone_renderer DANS CET ORDRE, sans jamais dupliquer leur
# logique. Si une règle métier doit changer, elle se change dans le
# composant concerné — jamais ici.
#
# Pipeline d'un tour de conversation (brief, section 5) :
#   1. Charger le contexte déjà connu           → api.db.get_context_fields
#   2. Identifier la dimension en cours          → question_planner
#   3. Extraire les informations de la réponse   → answer_extractor
#   4. Mettre à jour le contexte                 → api.db.upsert_context_field
#   5. Identifier la dimension suivante          → question_planner
#   6. Générer la réponse                        → tone_renderer
#   7. Sauvegarder les messages                  → api.db.save_context_message
# ═══════════════════════════════════════════════════════════════════════════

import uuid

import api.db as db
from agents.context_builder.schema import DIMENSION_BY_KEY, FIELD_LABEL_BY_KEY, missing_required_field_labels
from agents.context_builder import question_planner as qp
from agents.context_builder import answer_extractor as ae
from agents.context_builder import tone_renderer as tr

_INTRO_MESSAGE = (
    "Je connais déjà votre audience. Il me manque une chose : vous.\n\n"
    "Racontez-moi votre entreprise avec vos mots — ce que vous vendez, comment "
    "ça rapporte, ce que vous visez, et ce qui vous freine aujourd'hui. Pas "
    "besoin de plan ni d'ordre : je structure derrière."
)


def _fields_for_dimension(dimension_key: str, fields: dict) -> dict:
    dim = DIMENSION_BY_KEY.get(dimension_key) or {}
    keys = {f['key'] for f in dim.get('fields', [])}
    return {k: v for k, v in fields.items() if k in keys}


def _state_payload(user_id, session, fields):
    """Forme commune retournée par resume_or_start et handle_message —
    garde le contrat stable pour le frontend."""
    prog = qp.progression(fields)
    ready = qp.is_ready(fields)
    nxt = qp.next_dimension(fields)
    return {
        'session_id':        session['session_id'],
        'updated_context':   fields,
        'progression':       prog,
        'completion_score':  qp.completion_ratio(fields),
        'is_ready':          ready,
        'current_dimension': nxt['key'] if nxt else None,
    }


def resume_or_start(user_id: str, folder_id: str = '') -> dict:
    """Appelé au chargement de la page. Reprend la session active de
    l'utilisateur si elle existe (reprise de session), sinon en démarre une
    nouvelle et pose la première question."""
    session = db.get_active_context_session(user_id)
    fields = db.get_context_fields(user_id)

    if session:
        messages = db.get_context_messages(session['session_id'], user_id)
        payload = _state_payload(user_id, session, fields)
        payload['messages'] = [
            {'role': m['role'], 'content': m['content']} for m in messages
        ]
        payload['resumed'] = True
        return payload

    # Nouvelle session
    session_id = f"cbs_{uuid.uuid4().hex[:16]}"
    nxt = qp.next_dimension(fields)
    db.create_context_session(session_id, user_id, folder_id=folder_id)
    session = {'session_id': session_id}

    if nxt:
        # Pas de question de dimension accolée ici — l'invitation à la
        # présentation libre (brief section 2.1) doit rester une invitation
        # ouverte, pas être immédiatement réduite à la première question
        # d'une dimension précise. handle_message() détecte la toute
        # première réponse et scanne les 7 dimensions à la fois.
        db.update_context_session(session_id, user_id, current_dimension=nxt['key'])
        opening = _INTRO_MESSAGE
    else:
        opening = tr.render_completion(fields)

    db.save_context_message(session_id, user_id, 'assistant', opening,
                             dimension_key=nxt['key'] if nxt else '')

    payload = _state_payload(user_id, session, fields)
    payload['messages'] = [{'role': 'assistant', 'content': opening}]
    payload['resumed'] = False
    return payload


def handle_message(user_id: str, message: str) -> dict:
    """Traite un message utilisateur dans la session active — le cœur de
    /context-chat. Crée une session si aucune n'existe (défensif, ne devrait
    pas arriver en usage normal puisque resume_or_start tourne au chargement)."""
    session = db.get_active_context_session(user_id)
    fields = db.get_context_fields(user_id)

    if not session:
        session_id = f"cbs_{uuid.uuid4().hex[:16]}"
        db.create_context_session(session_id, user_id)
        session = {'session_id': session_id}

    session_id = session['session_id']
    current_dim = session.get('current_dimension') or (qp.next_dimension(fields) or {}).get('key')

    # Toute première réponse de la session = réponse à l'invitation libre
    # d'ouverture (brief section 2.1) → on scanne les 7 dimensions à la fois
    # au lieu de limiter l'extraction à la seule dimension "en cours". Toute
    # réponse suivante repasse par l'extraction ciblée habituelle.
    existing_messages   = db.get_context_messages(session_id, user_id)
    is_first_user_reply = not any(m.get('role') == 'user' for m in existing_messages)

    db.save_context_message(session_id, user_id, 'user', message, dimension_key=current_dim or '')

    if not current_dim:
        # Tout est déjà couvert — pas de dimension à traiter, on ne casse pas
        # pour autant : on répond simplement que le contexte est déjà complet.
        reply = tr.render_completion(fields)
        db.save_context_message(session_id, user_id, 'assistant', reply)
        payload = _state_payload(user_id, session, fields)
        payload['reply'] = reply
        payload['rejected_vague'] = []
        return payload

    if is_first_user_reply:
        result = ae.extract_answer_freeform(message, fields)
    else:
        known_for_dim = _fields_for_dimension(current_dim, fields)
        result = ae.extract_answer(current_dim, message, known_for_dim)
    extracted, rejected_vague = result['extracted'], result['rejected_vague']

    for key, value in extracted.items():
        db.upsert_context_field(user_id, key, value, source_session_id=session_id)

    fields = db.get_context_fields(user_id)  # relire après écriture — source de vérité
    nxt = qp.next_dimension(fields)
    dim_now = DIMENSION_BY_KEY.get(current_dim)

    if rejected_vague and not extracted:
        reply = tr.render_clarification(rejected_vague, dim_now['opening_question'] if dim_now else '')
        # On reste sur la même dimension — pas de progression tant que la
        # réponse n'est pas exploitable.
        db.update_context_session(session_id, user_id, current_dimension=current_dim)
    elif nxt and nxt['key'] == current_dim:
        # La dimension en cours n'est pas encore complète — on cible
        # uniquement ce qui manque au lieu de reposer la question d'ouverture
        # entière (voir tone_renderer.render_followup).
        missing_labels = missing_required_field_labels(current_dim, fields)
        reply = tr.render_followup(extracted, FIELD_LABEL_BY_KEY, missing_labels)
        db.update_context_session(session_id, user_id, current_dimension=current_dim)
    elif nxt:
        reply = tr.render_transition(extracted, FIELD_LABEL_BY_KEY, nxt['opening_question'])
        db.update_context_session(session_id, user_id, current_dimension=nxt['key'])
    else:
        reply = tr.render_completion(fields)
        db.update_context_session(session_id, user_id, status='active', current_dimension='')

    db.save_context_message(session_id, user_id, 'assistant', reply,
                             dimension_key=(nxt['key'] if nxt else ''))

    payload = _state_payload(user_id, session, fields)
    payload['reply'] = reply
    payload['rejected_vague'] = rejected_vague
    return payload
