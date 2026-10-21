# ─── Gabriel — Data Access Layer (Supabase + JSON fallback) ──────────────────
#
# Tables Supabase : gabriel_analyses, gabriel_strategies, gabriel_feedbacks, gabriel_exports,
#                   gabriel_survey_events, gabriel_survey_responses, gabriel_consent_records,
#                   gabriel_chat_conversations, gabriel_chat_messages, gabriel_training_candidates
# Fallback       : data/history.json (développement local)
# Accès         : UUID/analysis_id — jamais par index entier

import os
import json
import time
import uuid
import tempfile
import datetime

from core.admin_access import is_admin_user_id

_BASE_DIR     = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DATA_DIR     = os.path.join(_BASE_DIR, 'data')
_HISTORY_FILE    = os.path.join(_DATA_DIR, 'history.json')
_STRATEGIES_FILE = os.path.join(_DATA_DIR, 'strategies.json')
_FEEDBACKS_FILE  = os.path.join(_DATA_DIR, 'feedbacks.json')
_UX_SETTINGS_FILE = os.path.join(_DATA_DIR, 'ux_settings.json')
_CROSS_ANALYSES_FILE = os.path.join(_DATA_DIR, 'cross_analyses.json')

_T_ANALYSES    = 'gabriel_analyses'
_T_STRATEGIES  = 'gabriel_strategies'
_T_FEEDBACKS   = 'gabriel_feedbacks'
_T_EXPORTS     = 'gabriel_exports'
_T_USERS       = 'gabriel_users'
_T_SURVEY_EVT  = 'gabriel_survey_events'
_T_SURVEY_RESP = 'gabriel_survey_responses'
_T_CONSENT     = 'gabriel_consent_records'
_T_CHAT_CONV   = 'gabriel_chat_conversations'
_T_CHAT_MSG    = 'gabriel_chat_messages'
_T_TRAIN_CAND  = 'gabriel_training_candidates'
_T_FOLDERS     = 'gabriel_folders'
_T_CTX_SESSIONS = 'gabriel_context_sessions'
_T_CTX_MESSAGES = 'gabriel_context_messages'
_T_CTX_FIELDS   = 'gabriel_context_fields'
_T_MEMORY_CASES = 'gabriel_memory_cases'
_T_UX_SETTINGS  = 'gabriel_ux_settings'
_T_CROSS_ANALYSES = 'gabriel_cross_analyses'
_T_PSYCHO_SOURCES = 'gabriel_psychologue_sources'
_T_CROSS_SOURCES = 'gabriel_cross_analysis_sources'
_T_SOURCE_COMMENTS = 'gabriel_source_comments'

FREE_ANALYSES_LIMIT = 3

# Administrative privileges are resolved centrally from ADMIN_USER_IDS.
# Email addresses are deliberately ignored for authorization.

_supabase = None

# Continuité de lecture des workspaces. Un incident réseau ponctuel vers
# Supabase ne doit pas transformer un dossier déjà ouvert en faux 404 dans le
# shell V2. Ce cache est volontairement éphémère (processus local), strictement
# indexé par utilisateur et seulement alimenté après une lecture/écriture base
# réussie : il ne remplace jamais Supabase ni ne masque une suppression validée.
_folder_cache = {}


def _cache_folder(user_id, folder):
    """Mémorise une copie privée d'un dossier déjà confirmé par la base."""
    if not (user_id and isinstance(folder, dict) and folder.get('folder_id')):
        return
    cached = dict(folder)
    cached['user_id'] = user_id
    _folder_cache[(str(user_id), str(cached['folder_id']))] = cached


def _cached_folder(folder_id, user_id):
    cached = _folder_cache.get((str(user_id), str(folder_id)))
    return dict(cached) if isinstance(cached, dict) else None


def _cached_folders(user_id, limit):
    """Retourne les dossiers connus du seul utilisateur demandé, les plus récents d'abord."""
    rows = [
        dict(folder) for (cached_user_id, _), folder in _folder_cache.items()
        if cached_user_id == str(user_id) and isinstance(folder, dict)
    ]
    rows.sort(key=lambda folder: str(folder.get('updated_at') or ''), reverse=True)
    return rows[:max(int(limit or 0), 0)]


def init_db(client):
    global _supabase
    _supabase = client


def get_ux_settings(page_key):
    """Retourne le document UX global, ou None si la table n'est pas déployée."""
    if _supabase and page_key:
        try:
            res = _supabase.table(_T_UX_SETTINGS).select('*').eq(
                'page_key', page_key
            ).limit(1).execute()
            row = (res.data or [None])[0]
            if row:
                return row
        except Exception as e:
            print(f'[DB] get_ux_settings error: {e}')
    try:
        with open(_UX_SETTINGS_FILE, 'r', encoding='utf-8') as handle:
            return (json.load(handle) or {}).get(page_key)
    except (OSError, ValueError):
        return None


def _save_ux_local(page_key, row):
    try:
        try:
            with open(_UX_SETTINGS_FILE, 'r', encoding='utf-8') as handle:
                data = json.load(handle) or {}
        except (OSError, ValueError):
            data = {}
        data[page_key] = row
        with open(_UX_SETTINGS_FILE, 'w', encoding='utf-8') as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
        return True
    except OSError as e:
        print(f'[DB] _save_ux_local error: {e}')
        return False


def save_ux_draft(page_key, settings, updated_by):
    if not page_key:
        return False
    current = get_ux_settings(page_key) or {'page_key': page_key}
    row = {**current, 'page_key': page_key, 'draft': settings,
           'updated_by': updated_by,
           'updated_at': datetime.datetime.utcnow().isoformat()}
    if _supabase:
        try:
            _supabase.table(_T_UX_SETTINGS).upsert(row, on_conflict='page_key').execute()
            return True
        except Exception as e:
            print(f'[DB] save_ux_draft error: {e}')
    return _save_ux_local(page_key, row)


def publish_ux_settings(page_key, settings, updated_by):
    if not page_key:
        return None
    try:
        current = get_ux_settings(page_key) or {}
        history = current.get('history') if isinstance(current.get('history'), list) else []
        published = current.get('published') if isinstance(current.get('published'), dict) else {}
        version = int(current.get('version') or 0) + 1
        if published:
            history.append({
                'version': version - 1,
                'settings': published,
                'published_at': current.get('published_at'),
            })
        row = {
            'page_key': page_key, 'draft': settings, 'published': settings,
            'history': history[-20:], 'version': version,
            'updated_by': updated_by,
            'updated_at': datetime.datetime.utcnow().isoformat(),
            'published_at': datetime.datetime.utcnow().isoformat(),
        }
        if _supabase:
            try:
                _supabase.table(_T_UX_SETTINGS).upsert(row, on_conflict='page_key').execute()
                return row
            except Exception as e:
                print(f'[DB] publish_ux_settings Supabase error: {e}')
        return row if _save_ux_local(page_key, row) else None
    except Exception as e:
        print(f'[DB] publish_ux_settings error: {e}')
        return None


# ─────────────────────────────────────────────────────────────────────────────
# SESSIONS DE L'ORCHESTRATEUR
# Les tables existent déjà dans supabase/survey_migration.sql. Les fonctions
# retournent None/False sans Supabase afin que l'application utilise son repli
# JSON local de développement.
# ─────────────────────────────────────────────────────────────────────────────

def get_orchestrator_session_state(user_id, conversation_id, folder_id=None):
    """Retourne les messages et l'état de mission d'une conversation Gabriel.

    Les missions résident dans le mental model déjà persisté avec la
    conversation. On ne crée ainsi pas une table parallèle pour un état qui
    doit rester strictement isolé par utilisateur et workspace.
    """
    if not (_supabase and user_id and conversation_id):
        return None
    try:
        res = (
            _supabase.table(_T_CHAT_CONV)
            .select('id,metadata')
            .eq('id', conversation_id)
            .eq('user_id', user_id)
            .eq('agent', 'orchestrateur')
            .limit(1)
            .execute()
        )
        row = (res.data or [None])[0]
        # Une conversation absente est un état initial normal. Le contrat de
        # cette fonction doit rester complet afin que l'Orchestrateur puisse
        # démarrer une toute première discussion sans KeyError.
        if not row:
            return {'messages': [], 'mental_model': {}}
        metadata = row.get('metadata') if isinstance(row.get('metadata'), dict) else {}
        if (metadata.get('folder_id') or None) != (folder_id or None):
            return {'messages': [], 'mental_model': {}}
        messages = metadata.get('messages')
        mental_model = metadata.get('mental_model')
        return {
            'messages': messages[-20:] if isinstance(messages, list) else [],
            'mental_model': mental_model if isinstance(mental_model, dict) else {},
        }
    except Exception as e:
        print(f'[DB] get_orchestrator_session_state error: {e}')
        return None


def get_orchestrator_session(user_id, conversation_id, folder_id=None):
    """Compatibilité historique : retourne uniquement les messages."""
    state = get_orchestrator_session_state(user_id, conversation_id, folder_id)
    if state is None:
        return None
    return state.get('messages', [])


def save_orchestrator_session(user_id, conversation_id, folder_id, title,
                              messages, mental_model=None):
    if not (_supabase and user_id and conversation_id):
        return False
    now = datetime.datetime.utcnow().isoformat()
    row = {
        'id': conversation_id,
        'user_id': user_id,
        'agent': 'orchestrateur',
        'title': (title or 'Conversation Gabriel')[:120],
        'updated_at': now,
        'metadata': {
            'folder_id': folder_id,
            'messages': messages[-40:],
            'mental_model': mental_model or {},
            'is_training_allowed': False,
        },
    }
    try:
        _supabase.table(_T_CHAT_CONV).upsert(row, on_conflict='id').execute()
        return True
    except Exception as e:
        print(f'[DB] save_orchestrator_session error: {e}')
        return False


# ─────────────────────────────────────────────────────────────────────────────
# ANALYSES
# ─────────────────────────────────────────────────────────────────────────────

def _auth_active():
    return os.environ.get('AUTH_ENABLED', 'false').lower() == 'true'


def _owned_by(entry_owner, user_id):
    """Un enregistrement du repli local n'est visible que de son propriétaire.

    La clé Supabase du serveur contourne les règles d'accès de la base : quand
    Supabase échoue, ces fichiers deviennent la seule barrière entre deux
    utilisateurs. Sans authentification (poste de développement), les entrées
    sans propriétaire écrites par d'anciennes versions ('local' ou vide) restent
    visibles, pour ne rien perdre en local."""
    if user_id and entry_owner == user_id:
        return True
    if _auth_active():
        return False
    return not entry_owner or entry_owner == 'local' or not user_id


def get_history(user_id=None, limit=50, folder_id=None):
    """Liste des analyses (métadonnées only, pas le full_result).
    Si folder_id fourni, filtre par dossier pour isoler les espaces de travail."""
    if _supabase and user_id:
        try:
            q = (
                _supabase.table(_T_ANALYSES)
                .select('analysis_id,title,source,nb_commentaires,created_at,has_strategy')
                .eq('user_id', user_id)
            )
            if folder_id:
                q = q.eq('folder_id', folder_id)
            res = q.order('created_at', desc=True).limit(limit).execute()
            return res.data or []
        except Exception as e:
            print(f'[DB] get_history error: {e}')

    # Fallback JSON — renvoie les champs métadonnées seulement
    history = _load_json_history()
    return [
        {
            'analysis_id':     e.get('analysis_id', ''),
            'title':           e.get('video_title') or e.get('source', ''),
            'source':          e.get('source', ''),
            'nb_commentaires': e.get('nb_commentaires', 0),
            'created_at':      e.get('date', ''),
            'has_strategy':    bool(e.get('strategie_result')),
        }
        for e in history if _owned_by(e.get('user_id'), user_id)
    ]


def save_analysis(entry, user_id=None, folder_id=None):
    """Sauvegarde une analyse. entry = dict complet avec full_result."""
    analysis_id = entry.get('analysis_id') or str(uuid.uuid4())[:12]

    if _supabase and user_id:
        try:
            row = {
                'user_id':         user_id,
                'analysis_id':     analysis_id,
                'title':           entry.get('video_title') or entry.get('source', ''),
                'source':          entry.get('source', ''),
                'nb_commentaires': entry.get('nb_commentaires', 0),
                'input_data':      {k: entry.get(k) for k in ('source', 'contenu') if entry.get(k)},
                'result_data':     entry.get('full_result') or {},
                'has_strategy':    False,
                'created_at':      datetime.datetime.utcnow().isoformat(),
            }
            if folder_id:
                row['folder_id'] = folder_id
            _supabase.table(_T_ANALYSES).insert(row).execute()
            return
        except Exception as e:
            print(f'[DB] save_analysis Supabase error: {e}')

    # Fallback local — uniquement si Supabase est absent ou vient d'échouer.
    # Avant : ce fichier était réécrit en entier à CHAQUE analyse, même quand
    # Supabase réussissait (donc pour rien) — un vrai/faux disque de secours
    # jamais lu en production, mais dont la taille (et le coût de lecture +
    # réécriture complète) grossit sans limite à chaque appel.
    local_entry = dict(entry or {})
    if user_id:
        local_entry['user_id'] = user_id
    if folder_id:
        local_entry['folder_id'] = folder_id
    _save_json_entry(local_entry)


def get_analysis_by_id(analysis_id, user_id=None):
    """Retourne l'entrée complète (avec full_result) pour un analysis_id."""
    if _supabase and user_id and analysis_id:
        try:
            res = (
                _supabase.table(_T_ANALYSES)
                .select('*')
                .eq('analysis_id', analysis_id)
                .eq('user_id', user_id)
                .limit(1)
                .execute()
            )
            rows = res.data or []
            if rows:
                row = rows[0]
                return {
                    'analysis_id':     row.get('analysis_id'),
                    'full_result':     row.get('result_data') or {},
                    'strategie_result': row.get('strategy_result') or {},
                    'source':          row.get('source', ''),
                    'title':           row.get('title', ''),
                    'date':            row.get('created_at', ''),
                    'folder_id':       row.get('folder_id', ''),
                }
        except Exception as e:
            print(f'[DB] get_analysis_by_id error: {e}')

    # Fallback JSON — toujours filtrer par user_id si disponible
    for entry in _load_json_history():
        if entry.get('analysis_id') != analysis_id:
            continue
        # Isolation : si l'entrée a un user_id et qu'on en a un, vérifier
        entry_uid = entry.get('user_id')
        if user_id and entry_uid and entry_uid != user_id:
            return None  # accès refusé
        return entry
    return None


# ─────────────────────────────────────────────────────────────────────────────
# CROSS ANALYSES DU PSYCHOLOGUE
#
# Une Cross Analyse est un read-model multi-source. Les analyses individuelles
# restent dans gabriel_analyses exactement comme avant ; cette couche les relie
# par analysis_id et conserve la provenance primaire des commentaires.
# ─────────────────────────────────────────────────────────────────────────────

def _load_json_cross_analyses():
    try:
        with open(_CROSS_ANALYSES_FILE, 'r', encoding='utf-8') as handle:
            payload = json.load(handle)
            return payload if isinstance(payload, list) else []
    except (OSError, ValueError):
        return []


def _write_json_cross_analyses(rows):
    # Écriture atomique : un crash pendant json.dump() sur le fichier final
    # laissait un JSON tronqué, et _load_json_cross_analyses() perdait alors
    # silencieusement TOUT l'historique Cross (ValueError → []). Écrire sur un
    # fichier temporaire puis os.replace() garantit que le fichier cible est
    # soit l'ancienne version complète, soit la nouvelle — jamais un état
    # intermédiaire corrompu.
    os.makedirs(_DATA_DIR, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(
        dir=_DATA_DIR, prefix='.cross_analyses.', suffix='.tmp',
    )
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as handle:
            json.dump(rows, handle, ensure_ascii=False, indent=2, default=str)
        os.replace(tmp_path, _CROSS_ANALYSES_FILE)
    except BaseException:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def _cross_local_row(cross_analysis_id, user_id=None):
    for row in _load_json_cross_analyses():
        if row.get('cross_analysis_id') != cross_analysis_id:
            continue
        if user_id and row.get('user_id') and row.get('user_id') != user_id:
            return None
        return row
    return None


def _source_snapshot(source):
    """Copie compacte de l'identité d'une source, sans commentaires."""
    if not isinstance(source, dict):
        return {}
    return {
        key: source.get(key) for key in (
            'source_id', 'position', 'platform', 'source_type', 'external_id',
            'video_id', 'input_url', 'canonical_url', 'label', 'metadata',
        ) if source.get(key) not in (None, '')
    }


def create_cross_analysis(cross_analysis_id, user_id, sources, *, folder_id=None,
                          options=None, job_id='', schema_version='1.0',
                          pipeline_version='cross-v1'):
    """Crée une session Cross sans modifier les analyses simples.

    Retourne True si Supabase est complet, False si le repli JSON local a été
    utilisé. Dans les deux cas, l'appelant peut continuer le job : le repli est
    conforme au comportement historique de ``save_analysis`` en développement.
    """
    if not (cross_analysis_id and user_id and isinstance(sources, list)):
        return False
    now = datetime.datetime.utcnow().isoformat()
    snapshots = [_source_snapshot(source) for source in sources]
    initial_result = {
        'options': dict(options or {}),
        'source_definitions': snapshots,
    }
    master = {
        'cross_analysis_id': cross_analysis_id,
        'user_id': user_id,
        'folder_id': folder_id or '',
        'job_id': job_id or '',
        'status': 'prepared',
        'schema_version': schema_version or '1.0',
        'pipeline_version': pipeline_version or 'cross-v1',
        'source_count': len(snapshots),
        'result_data': initial_result,
        'created_at': now,
        'updated_at': now,
    }

    if _supabase:
        try:
            _supabase.table(_T_CROSS_ANALYSES).insert(master).execute()
            for source in snapshots:
                source_id = source.get('source_id')
                if not source_id:
                    continue
                _supabase.table(_T_PSYCHO_SOURCES).upsert({
                    'source_id': source_id,
                    'user_id': user_id,
                    'platform': source.get('platform') or 'youtube',
                    'external_id': source.get('external_id') or source.get('video_id') or '',
                    'canonical_url': source.get('canonical_url') or source.get('input_url') or '',
                    'source_metadata': source.get('metadata') or {},
                }, on_conflict='source_id').execute()
                _supabase.table(_T_CROSS_SOURCES).upsert({
                    'cross_analysis_id': cross_analysis_id,
                    'source_id': source_id,
                    'user_id': user_id,
                    'analysis_id': '',
                    'position': int(source.get('position') or 0),
                    'status': 'prepared',
                    'source_snapshot': source,
                    'source_analysis': {},
                }, on_conflict='cross_analysis_id,source_id').execute()
            return True
        except Exception as e:
            # La migration Cross peut ne pas être appliquée dans un environnement
            # local. Comme le reste de cette DAL, garder un repli fonctionnel
            # est plus sûr que casser l'analyse simple ou le job courant.
            print(f'[DB] create_cross_analysis error: {e}')
            # Compensation : ces écritures ne sont pas transactionnelles (pas de
            # RPC Supabase pour l'instant). Sans nettoyage, un échec à mi-chemin
            # laissait une ligne maître avec ``source_count`` annonçant N sources
            # alors qu'aucune (ou une partie seulement) n'existait réellement —
            # un état orphelin invisible pour get_cross_analysis(). On retire ce
            # qui a pu être écrit pour CETTE session avant de retomber sur le
            # JSON local, qui repart alors d'un état propre.
            try:
                _supabase.table(_T_CROSS_SOURCES).delete().eq(
                    'cross_analysis_id', cross_analysis_id).execute()
                _supabase.table(_T_CROSS_ANALYSES).delete().eq(
                    'cross_analysis_id', cross_analysis_id).execute()
            except Exception as cleanup_exc:
                print(f'[DB] create_cross_analysis cleanup_error: {cleanup_exc}')

    rows = _load_json_cross_analyses()
    rows = [row for row in rows if row.get('cross_analysis_id') != cross_analysis_id]
    master['source_records'] = [
        {'source_snapshot': source, 'status': 'prepared', 'analysis_id': '', 'source_analysis': {}}
        for source in snapshots
    ]
    rows.append(master)
    _write_json_cross_analyses(rows)
    return False


def update_cross_analysis(cross_analysis_id, user_id, **fields):
    """Met à jour uniquement les champs autorisés d'une session Cross."""
    if not (cross_analysis_id and user_id):
        return False
    allowed = {
        'job_id', 'status', 'result_data', 'error_message', 'schema_version',
        'pipeline_version', 'model_version', 'embedding_version', 'source_count',
    }
    payload = {key: value for key, value in fields.items() if key in allowed}
    if not payload:
        return False
    payload['updated_at'] = datetime.datetime.utcnow().isoformat()
    if _supabase:
        # Ce write porte le résultat final d'une Cross Analyse (LLM déjà
        # payé, calcul déjà fait) : un blip réseau transitoire ([Errno 35]
        # "Resource temporarily unavailable" observé en conditions réelles,
        # sur une fenêtre de plusieurs secondes à chaque fois) ne doit pas
        # faire perdre silencieusement un travail terminé et laisser le job
        # bloqué à "running" pour toujours. Fenêtre de ré-essai plus longue
        # que _call_youtube_with_retry (services/scraper.py) : ce write-ci
        # est le seul qui livre le résultat à l'utilisateur, donc insister
        # un peu plus avant d'abandonner coûte moins cher qu'un résultat
        # perdu après plusieurs minutes de pipeline (scraping + LLM).
        max_attempts = 5
        last_exc = None
        for attempt in range(max_attempts):
            try:
                _supabase.table(_T_CROSS_ANALYSES).update(payload)\
                    .eq('cross_analysis_id', cross_analysis_id).eq('user_id', user_id).execute()
                return True
            except Exception as e:
                last_exc = e
                if attempt < max_attempts - 1:
                    time.sleep(min(3 * (2 ** attempt), 20))
                    continue
        print(f'[DB] update_cross_analysis error (après {max_attempts} essais) : {last_exc}')

    rows = _load_json_cross_analyses()
    for row in rows:
        if row.get('cross_analysis_id') == cross_analysis_id and row.get('user_id') == user_id:
            row.update(payload)
            _write_json_cross_analyses(rows)
            return True
    return False


def update_cross_analysis_source(cross_analysis_id, user_id, source_id, *, status=None,
                                 analysis_id=None, source_snapshot=None,
                                 source_analysis=None):
    """Persiste l'état d'une source sans mélanger son résultat aux autres."""
    if not (cross_analysis_id and user_id and source_id):
        return False
    payload = {}
    if status is not None:
        payload['status'] = str(status)[:80]
    if analysis_id is not None:
        payload['analysis_id'] = str(analysis_id)[:120]
    if isinstance(source_snapshot, dict):
        payload['source_snapshot'] = source_snapshot
    if isinstance(source_analysis, dict):
        payload['source_analysis'] = source_analysis
    if not payload:
        return False

    if _supabase:
        try:
            _supabase.table(_T_CROSS_SOURCES).update(payload)\
                .eq('cross_analysis_id', cross_analysis_id).eq('source_id', source_id)\
                .eq('user_id', user_id).execute()
            return True
        except Exception as e:
            print(f'[DB] update_cross_analysis_source error: {e}')

    rows = _load_json_cross_analyses()
    for row in rows:
        if row.get('cross_analysis_id') != cross_analysis_id or row.get('user_id') != user_id:
            continue
        records = row.setdefault('source_records', [])
        for record in records:
            snapshot = record.get('source_snapshot') or {}
            if snapshot.get('source_id') == source_id:
                record.update(payload)
                _write_json_cross_analyses(rows)
                return True
        records.append({'source_snapshot': {'source_id': source_id}, **payload})
        _write_json_cross_analyses(rows)
        return True
    return False


def save_cross_source_comments(user_id, source, comments, *, cross_analysis_id=''):
    """Sauvegarde la preuve primaire de *cette* source, jamais un corpus mixé."""
    if not (user_id and isinstance(source, dict) and isinstance(comments, list)):
        return False
    source_id = source.get('source_id')
    if not source_id:
        return False
    if not _supabase:
        # En développement, conserver également la preuve primaire ; sans
        # elle le repli local ne respecterait pas le même contrat de
        # traçabilité que Supabase.
        if not cross_analysis_id:
            return False
        rows = _load_json_cross_analyses()
        for cross in rows:
            if cross.get('cross_analysis_id') != cross_analysis_id or cross.get('user_id') != user_id:
                continue
            for record in cross.get('source_records', []):
                snapshot = record.get('source_snapshot') or {}
                if snapshot.get('source_id') == source_id:
                    record['raw_comments'] = list(comments[:250])
                    _write_json_cross_analyses(rows)
                    return True
        return False
    try:
        source_row = {
            'source_id': source_id,
            'user_id': user_id,
            'platform': source.get('platform') or 'youtube',
            'external_id': source.get('external_id') or source.get('video_id') or '',
            'canonical_url': source.get('canonical_url') or source.get('input_url') or '',
            'source_metadata': source.get('metadata') or {},
        }
        _supabase.table(_T_PSYCHO_SOURCES).upsert(source_row, on_conflict='source_id').execute()
        rows = []
        for comment in comments[:250]:
            if not isinstance(comment, dict) or not comment.get('comment_id') or not comment.get('text'):
                continue
            try:
                likes = max(0, int(comment.get('likes') or 0))
            except (TypeError, ValueError):
                likes = 0
            rows.append({
                'comment_id': str(comment['comment_id'])[:220],
                'source_id': source_id,
                'user_id': user_id,
                'external_comment_id': str(comment.get('external_comment_id') or '')[:180],
                'video_id': str(comment.get('video_id') or source.get('video_id') or '')[:160],
                'text': str(comment.get('text') or '')[:10000],
                'author': str(comment.get('author') or '')[:300],
                'likes': likes,
                'comment_metadata': comment.get('metadata') if isinstance(comment.get('metadata'), dict) else {},
            })
        if rows:
            _supabase.table(_T_SOURCE_COMMENTS).upsert(rows, on_conflict='comment_id').execute()
        return True
    except Exception as e:
        print(f'[DB] save_cross_source_comments error: {e}')
        return False


def list_cross_analyses(user_id, limit=30):
    """Cross Analyses d'un utilisateur, plus récentes d'abord, en vue légère
    pour le menu : identité des vidéos comparées, sans résultat détaillé."""
    if not user_id:
        return []
    rows = []
    if _supabase:
        try:
            res = _supabase.table(_T_CROSS_ANALYSES)\
                .select('cross_analysis_id,status,source_count,created_at,updated_at,folder_id')\
                .eq('user_id', user_id).order('created_at', desc=True).limit(limit).execute()
            rows = res.data or []
            ids = [r['cross_analysis_id'] for r in rows]
            links = []
            if ids:
                links = (_supabase.table(_T_CROSS_SOURCES)
                         .select('cross_analysis_id,position,source_snapshot')
                         .eq('user_id', user_id).in_('cross_analysis_id', ids).execute().data or [])
            for row in rows:
                row['source_records'] = sorted(
                    [l for l in links if l.get('cross_analysis_id') == row['cross_analysis_id']],
                    key=lambda l: int(l.get('position') or 0))
        except Exception as e:
            print(f'[DB] list_cross_analyses error: {e}')
            rows = []
    if not rows:
        rows = [r for r in _load_json_cross_analyses() if r.get('user_id') == user_id]
        rows.sort(key=lambda r: r.get('created_at') or '', reverse=True)
        rows = rows[:limit]
    return [{
        'cross_analysis_id': r.get('cross_analysis_id'),
        'status': r.get('status', 'prepared'),
        'created_at': r.get('created_at'),
        'folder_id': r.get('folder_id', ''),
        'sources': [{
            'title': ((rec.get('source_snapshot') or {}).get('metadata') or {}).get('title')
                     or (rec.get('source_snapshot') or {}).get('label', ''),
            'platform': (rec.get('source_snapshot') or {}).get('platform', ''),
        } for rec in (r.get('source_records') or []) if isinstance(rec, dict)],
    } for r in rows]


def get_cross_analysis(cross_analysis_id, user_id=None):
    """Retourne une Cross et son état source par source, cloisonnés par user."""
    if not cross_analysis_id:
        return None
    if _supabase and user_id:
        try:
            result = _supabase.table(_T_CROSS_ANALYSES).select('*')\
                .eq('cross_analysis_id', cross_analysis_id).eq('user_id', user_id).limit(1).execute()
            row = (result.data or [None])[0]
            if not row:
                return None
            links = _supabase.table(_T_CROSS_SOURCES).select('*')\
                .eq('cross_analysis_id', cross_analysis_id).eq('user_id', user_id)\
                .order('position').execute()
            row['source_records'] = links.data or []
            return row
        except Exception as e:
            print(f'[DB] get_cross_analysis error: {e}')
    return _cross_local_row(cross_analysis_id, user_id)


def get_cross_analysis_source(cross_analysis_id, source_id, user_id=None):
    """Retourne une analyse individuelle Cross sans exposer les autres sources."""
    if not (cross_analysis_id and source_id):
        return None
    if _supabase and user_id:
        try:
            result = _supabase.table(_T_CROSS_SOURCES).select('*')\
                .eq('cross_analysis_id', cross_analysis_id).eq('source_id', source_id)\
                .eq('user_id', user_id).limit(1).execute()
            row = (result.data or [None])[0]
            if row:
                return row
        except Exception as e:
            print(f'[DB] get_cross_analysis_source error: {e}')
    cross = get_cross_analysis(cross_analysis_id, user_id) or _cross_local_row(cross_analysis_id, user_id)
    for record in (cross or {}).get('source_records', []):
        if (record.get('source_snapshot') or {}).get('source_id') == source_id:
            return record
    # Repli de lecture : si le résultat final a été sauvegardé mais que la
    # table de liens vient juste d'être migrée, l'analyse détaillée reste
    # accessible depuis le read-model maître.
    source_definitions = ((cross or {}).get('result_data') or {}).get('source_definitions') or []
    source_analyses = ((cross or {}).get('result_data') or {}).get('source_analyses') or []
    source_analysis = next(
        (item for item in source_analyses if isinstance(item, dict) and item.get('source_id') == source_id),
        {},
    )
    snapshot = next(
        (item for item in source_definitions if isinstance(item, dict) and item.get('source_id') == source_id),
        {},
    )
    if source_analysis or snapshot:
        return {
            'source_snapshot': snapshot,
            'source_analysis': source_analysis,
            'analysis_id': source_analysis.get('analysis_id', ''),
            'status': 'completed' if source_analysis else 'prepared',
        }
    return None


def get_cross_source_comments(cross_analysis_id, source_id, user_id=None, limit=50):
    """Lit les commentaires d'une source, toujours filtrés par user et source."""
    if not (cross_analysis_id and source_id):
        return []
    try:
        safe_limit = max(1, min(int(limit), 250))
    except (TypeError, ValueError):
        safe_limit = 50
    if _supabase and user_id:
        try:
            result = _supabase.table(_T_SOURCE_COMMENTS)\
                .select('comment_id,source_id,external_comment_id,video_id,text,author,likes,comment_metadata,created_at')\
                .eq('source_id', source_id).eq('user_id', user_id)\
                .order('likes', desc=True).limit(safe_limit).execute()
            return result.data or []
        except Exception as e:
            print(f'[DB] get_cross_source_comments error: {e}')
    source = get_cross_analysis_source(cross_analysis_id, source_id, user_id) or {}
    return list(source.get('raw_comments') or [])[:safe_limit]


def get_cross_analysis_evidence(cross_analysis_id, insight_id, user_id=None):
    """Résout une preuve par insight_id depuis le résultat Cross persisté."""
    cross = get_cross_analysis(cross_analysis_id, user_id)
    result = (cross or {}).get('result_data') or {}
    evidence = result.get('evidence_index') if isinstance(result, dict) else {}
    return evidence.get(insight_id) if isinstance(evidence, dict) else None


# ─────────────────────────────────────────────────────────────────────────────
# JOBS D'ANALYSE (persistance — survit aux redémarrages Render)
# ─────────────────────────────────────────────────────────────────────────────

_T_JOBS = 'gabriel_analysis_jobs'


def create_job(job_id, user_id, analysis_id='', folder_id=None):
    """Crée un job en base (status=pending). Retourne True si persisté en DB."""
    if not (_supabase and user_id):
        return False
    try:
        row = {
            'job_id':      job_id,
            'user_id':     user_id,
            'analysis_id': analysis_id,
            'status':      'pending',
            'progress':    0,
            'step':        'created',
        }
        if folder_id:
            row['folder_id'] = folder_id
        _supabase.table(_T_JOBS).insert(row).execute()
        print(f'[JOB] saved_to_db job_id={job_id}')
        return True
    except Exception as e:
        print(f'[DB] create_job error: {e}')
        return False


def update_job(job_id, user_id=None, status=None, progress=None, step=None,
               error_message=None, result_data=None, completed=False):
    """Met à jour un job. Chaque champ est optionnel. updated_at sert de heartbeat."""
    if not (_supabase and job_id):
        return False
    fields = {'updated_at': datetime.datetime.utcnow().isoformat()}
    if status is not None:
        fields['status'] = status
    if progress is not None:
        fields['progress'] = int(progress)
    if step is not None:
        fields['step'] = str(step)[:200]
    if error_message is not None:
        fields['error_message'] = str(error_message)[:500]
    if result_data is not None:
        fields['result_data'] = result_data
    if completed:
        fields['completed_at'] = datetime.datetime.utcnow().isoformat()
    try:
        q = _supabase.table(_T_JOBS).update(fields).eq('job_id', job_id)
        if user_id:
            q = q.eq('user_id', user_id)
        q.execute()
        return True
    except Exception as e:
        print(f'[DB] update_job error: {e}')
        return False


def mark_stale_jobs_interrupted(min_age_seconds=120):
    """Passe en « interrupted » les travaux restés « pending/running » sans
    battement de cœur depuis plus de min_age_seconds (analyses, générations
    et Cross Analyses). Le thread qui les faisait avancer est mort avec le
    serveur : sans ce balayage, un travail jamais relu restait « en cours »
    pour toujours (24/09/2026 : 3 analyses et 1 Cross bloquées depuis août).
    Le délai évite de toucher un travail qu'un autre processus fait encore
    avancer. Retourne {'jobs': n, 'cross': n}."""
    counts = {'jobs': 0, 'cross': 0}
    if not _supabase:
        return counts
    now = datetime.datetime.utcnow()
    cutoff = (now - datetime.timedelta(seconds=min_age_seconds)).isoformat()
    message = 'Interrompu par un redémarrage du serveur.'
    for key, table, extra in (
        ('jobs', _T_JOBS, {'completed_at': now.isoformat()}),
        ('cross', _T_CROSS_ANALYSES, {}),
    ):
        try:
            res = _supabase.table(table)\
                .update({'status': 'interrupted', 'error_message': message, 'updated_at': now.isoformat(), **extra})\
                .in_('status', ['pending', 'running']).lt('updated_at', cutoff).execute()
            counts[key] = len(res.data or [])
        except Exception as e:
            print(f'[DB] mark_stale_jobs_interrupted({table}) error: {e}')
    return counts


def get_job(job_id, user_id=None):
    """Récupère un job par job_id (filtré par user_id). None si introuvable."""
    if not (_supabase and job_id):
        return None
    try:
        q = _supabase.table(_T_JOBS).select('*').eq('job_id', job_id)
        if user_id:
            q = q.eq('user_id', user_id)
        rows = (q.limit(1).execute()).data or []
        return rows[0] if rows else None
    except Exception as e:
        print(f'[DB] get_job error: {e}')
        return None


def update_analysis_strategy(analysis_id, strategy_result, strategy_id=None, user_id=None):
    """Attache le résultat stratégique à une analyse existante."""
    if _supabase and user_id and analysis_id:
        try:
            payload = {'has_strategy': True, 'strategy_result': strategy_result}
            if strategy_id:
                payload['strategy_id'] = strategy_id
            _supabase.table(_T_ANALYSES)\
                .update(payload)\
                .eq('analysis_id', analysis_id)\
                .eq('user_id', user_id)\
                .execute()
            return
        except Exception as e:
            print(f'[DB] update_analysis_strategy error: {e}')

    # Fallback JSON — uniquement si Supabase est absent ou a échoué. Avant :
    # relecture + réécriture complète du fichier local à chaque génération de
    # stratégie, même quand Supabase avait déjà réussi.
    history = _load_json_history()
    for e in history:
        if e.get('analysis_id') == analysis_id and _owned_by(e.get('user_id'), user_id):
            e['strategie_result'] = strategy_result
            e['has_strategy'] = True
            break
    _write_json_history(history)


def delete_analysis(analysis_id, user_id=None):
    """Supprime une analyse par analysis_id."""
    if _supabase and user_id and analysis_id:
        try:
            _supabase.table(_T_ANALYSES)\
                .delete()\
                .eq('analysis_id', analysis_id)\
                .eq('user_id', user_id)\
                .execute()
            return True
        except Exception as e:
            print(f'[DB] delete_analysis error: {e}')

    history = _load_json_history()
    original_len = len(history)
    history = [e for e in history if not (e.get('analysis_id') == analysis_id and _owned_by(e.get('user_id'), user_id))]
    _write_json_history(history)
    return len(history) < original_len


# ─────────────────────────────────────────────────────────────────────────────
# STRATEGIES
# ─────────────────────────────────────────────────────────────────────────────

def _strategy_title(strategy_data):
    """Dérive un titre lisible depuis le contenu de la stratégie."""
    if not isinstance(strategy_data, dict):
        return 'Stratégie'
    for key in ('decision_centrale', 'message_central', 'objectif_utilisateur_reformule'):
        val = (strategy_data.get(key) or '').strip()
        if val:
            return val[:90]
    offre = strategy_data.get('offre_recommandee') or {}
    if isinstance(offre, dict) and offre.get('nom'):
        return str(offre['nom'])[:90]
    return 'Stratégie'


def save_strategy(strategy_data, user_id=None, analysis_id=None, business_context=None, folder_id=None):
    """
    Sauvegarde une stratégie comme enregistrement de premier ordre.
    Persiste dans Supabase (si user connecté) ET dans le fallback JSON local.
    Retourne le strategy_id.
    """
    strategy_id = str(uuid.uuid4())[:16]
    created_at  = datetime.datetime.utcnow().isoformat()
    title       = _strategy_title(strategy_data)

    saved_to_supabase = False
    if _supabase and user_id:
        try:
            row = {
                'user_id':          user_id,
                'strategy_id':      strategy_id,
                'analysis_id':      analysis_id or '',
                'business_context': business_context or {},
                'strategy_result':  strategy_data or {},
                'created_at':       created_at,
            }
            if folder_id:
                row['folder_id'] = folder_id
            _supabase.table(_T_STRATEGIES).insert(row).execute()
            saved_to_supabase = True
        except Exception as e:
            print(f'[DB] save_strategy Supabase error: {e}')

    # Fallback JSON — uniquement si Supabase est absent ou a échoué (dev +
    # offline). Avant : jusqu'à 200 stratégies complètes (chacune un JSON
    # dense — décision, offre, pricing, plan 90 jours...) relues et
    # réécrites en entier sur DISQUE à chaque génération, même quand
    # Supabase venait de réussir et que ce fichier n'est jamais lu en
    # production — le coût le plus élevé trouvé parmi les bugs de vitesse.
    if not saved_to_supabase:
        try:
            rows = _load_json_strategies()
            rows = [r for r in rows if r.get('strategy_id') != strategy_id]
            rows.insert(0, {
                'user_id':          user_id or 'local',
                'strategy_id':      strategy_id,
                'analysis_id':      analysis_id or '',
                'folder_id':        folder_id or '',
                'title':            title,
                'business_context': business_context or {},
                'strategy_result':  strategy_data or {},
                'created_at':       created_at,
            })
            _write_json_strategies(rows[:200])
        except Exception as e:
            print(f'[DB] save_strategy JSON error: {e}')

    return strategy_id


def _attach_feedback(item, fb_index):
    """Ajoute usefulness/resultat à une stratégie depuis l'index feedback."""
    fb = fb_index['by_strategy'].get(item.get('strategy_id')) \
         or (fb_index['by_analysis'].get(item.get('analysis_id')) if item.get('analysis_id') else None)
    item['usefulness'] = (fb or {}).get('usefulness', '')
    item['resultat']   = (fb or {}).get('resultat', '')
    return item


def get_strategies(user_id=None, limit=50, folder_id=None):
    """Liste des stratégies de l'utilisateur (métadonnées + statut feedback).
    Si folder_id fourni, filtre par dossier pour isoler les espaces de travail."""
    fb_index = _feedback_index(user_id)

    if _supabase and user_id:
        try:
            q = (
                _supabase.table(_T_STRATEGIES)
                .select('strategy_id,analysis_id,folder_id,strategy_result,created_at')
                .eq('user_id', user_id)
            )
            if folder_id:
                q = q.eq('folder_id', folder_id)
            res = q.order('created_at', desc=True).limit(limit).execute()
            return [_attach_feedback({
                'strategy_id': r.get('strategy_id'),
                'analysis_id': r.get('analysis_id', ''),
                'folder_id':   r.get('folder_id', ''),
                'title':       _strategy_title(r.get('strategy_result') or {}),
                'created_at':  r.get('created_at', ''),
            }, fb_index) for r in (res.data or [])]
        except Exception as e:
            print(f'[DB] get_strategies error: {e}')

    # Fallback JSON — uniquement les stratégies de cet utilisateur
    rows = [r for r in _load_json_strategies() if _owned_by(r.get('user_id'), user_id)]
    return [_attach_feedback({
        'strategy_id': r.get('strategy_id'),
        'analysis_id': r.get('analysis_id', ''),
        'folder_id':   r.get('folder_id', ''),
        'title':       r.get('title') or _strategy_title(r.get('strategy_result') or {}),
        'created_at':  r.get('created_at', ''),
    }, fb_index) for r in rows[:limit]]


def get_strategy_by_id(strategy_id, user_id=None):
    """Retourne une stratégie complète par son strategy_id."""
    if _supabase and user_id and strategy_id:
        try:
            res = (
                _supabase.table(_T_STRATEGIES)
                .select('*')
                .eq('strategy_id', strategy_id)
                .eq('user_id', user_id)
                .limit(1)
                .execute()
            )
            rows = res.data or []
            if rows:
                r = rows[0]
                return {
                    'strategy_id':      r.get('strategy_id'),
                    'analysis_id':      r.get('analysis_id', ''),
                    'folder_id':        r.get('folder_id', ''),
                    'title':            _strategy_title(r.get('strategy_result') or {}),
                    'business_context': r.get('business_context') or {},
                    'strategy_result':  r.get('strategy_result') or {},
                    'created_at':       r.get('created_at', ''),
                }
        except Exception as e:
            print(f'[DB] get_strategy_by_id error: {e}')

    # Fallback JSON — jamais la stratégie d'un autre utilisateur
    for r in _load_json_strategies():
        if r.get('strategy_id') == strategy_id and _owned_by(r.get('user_id'), user_id):
            return r
    return None


def delete_strategy(strategy_id, user_id=None):
    """Supprime une stratégie par strategy_id."""
    if _supabase and user_id and strategy_id:
        try:
            _supabase.table(_T_STRATEGIES)\
                .delete()\
                .eq('strategy_id', strategy_id)\
                .eq('user_id', user_id)\
                .execute()
        except Exception as e:
            print(f'[DB] delete_strategy error: {e}')

    rows = _load_json_strategies()
    new_rows = [r for r in rows if not (r.get('strategy_id') == strategy_id and _owned_by(r.get('user_id'), user_id))]
    _write_json_strategies(new_rows)
    return len(new_rows) < len(rows)


# ─────────────────────────────────────────────────────────────────────────────
# FEEDBACKS
# ─────────────────────────────────────────────────────────────────────────────

def save_feedback(feedback_data, user_id=None, analysis_id=None, strategy_id=None):
    """
    Sauvegarde un feedback utilisateur (Supabase + fallback JSON).
    Deux dimensions :
      - usefulness : 'oui' | 'partiellement' | 'non'   (pertinence perçue)
      - resultat   : 'fonctionne' | 'sans_resultat' | 'pas_teste'  (résultat terrain)
    """
    usefulness = feedback_data.get('usefulness', '') or feedback_data.get('pertinente', '')
    resultat   = feedback_data.get('resultat', '')
    comment    = feedback_data.get('comment', '') or feedback_data.get('pourquoi', '')
    score_map  = {'oui': 5, 'partiellement': 3, 'non': 1, 'positif': 5, 'negatif': 1}
    score      = score_map.get((usefulness or '').lower(), None)
    was_useful = (usefulness or '').lower() in ('oui', 'positif', 'yes')
    created_at = datetime.datetime.utcnow().isoformat()
    ok = False

    if _supabase and user_id:
        try:
            row = {
                'user_id':          user_id or 'anonymous',
                'analysis_id':      analysis_id or '',
                'strategy_id':      strategy_id or '',
                'usefulness_score': score,
                'was_useful':       was_useful if usefulness else None,
                'comment':          comment,
                'raw_data':         {**feedback_data, 'resultat': resultat},
                'created_at':       created_at,
            }
            _supabase.table(_T_FEEDBACKS).insert(row).execute()
            ok = True
        except Exception as e:
            print(f'[DB] save_feedback Supabase error: {e}')

    # Fallback JSON — uniquement si Supabase est absent ou a échoué. Avant :
    # relu + réécrit en entier (jusqu'à 500 entrées) à chaque feedback, même
    # quand Supabase avait déjà réussi (ok était déjà True).
    if not ok:
        try:
            rows = _load_json_feedbacks()
            rows.insert(0, {
                'user_id':     user_id or 'local',
                'analysis_id': analysis_id or '',
                'strategy_id': strategy_id or '',
                'usefulness':  usefulness,
                'resultat':    resultat,
                'comment':     comment,
                'created_at':  created_at,
            })
            _write_json_feedbacks(rows[:500])
            ok = True
        except Exception as e:
            print(f'[DB] save_feedback JSON error: {e}')

    return ok


def get_feedbacks(user_id=None, limit=200):
    """Retourne tous les feedbacks (le plus récent en premier)."""
    if _supabase and user_id:
        try:
            res = (
                _supabase.table(_T_FEEDBACKS)
                .select('analysis_id,strategy_id,usefulness_score,was_useful,comment,raw_data,created_at')
                .eq('user_id', user_id)
                .order('created_at', desc=True)
                .limit(limit)
                .execute()
            )
            out = []
            for r in (res.data or []):
                raw = r.get('raw_data') or {}
                out.append({
                    'analysis_id': r.get('analysis_id', ''),
                    'strategy_id': r.get('strategy_id', ''),
                    'usefulness':  raw.get('usefulness') or raw.get('pertinente') or '',
                    'resultat':    raw.get('resultat', ''),
                    'comment':     r.get('comment', ''),
                    'created_at':  r.get('created_at', ''),
                })
            return out
        except Exception as e:
            print(f'[DB] get_feedbacks error: {e}')

    return [f for f in _load_json_feedbacks() if _owned_by(f.get('user_id'), user_id)][:limit]


def _feedback_index(user_id=None):
    """
    Indexe le dernier feedback par strategy_id et par analysis_id.
    Retourne {'by_strategy': {...}, 'by_analysis': {...}}.
    Les feedbacks étant triés du plus récent au plus ancien, on garde le premier vu.
    """
    by_strategy, by_analysis = {}, {}
    for f in get_feedbacks(user_id):
        sid, aid = f.get('strategy_id'), f.get('analysis_id')
        if sid and sid not in by_strategy:
            by_strategy[sid] = f
        if aid and aid not in by_analysis:
            by_analysis[aid] = f
    return {'by_strategy': by_strategy, 'by_analysis': by_analysis}


# ─────────────────────────────────────────────────────────────────────────────
# PLAN / LIMITES UTILISATEUR
# ─────────────────────────────────────────────────────────────────────────────

def get_user_plan(user_id):
    """
    Retourne le plan de l'utilisateur : 'free' | 'early_access' | 'standard' | 'pme'
    (voir app.py _STRIPE_PLANS — stratégie pricing sans freemium permanent).
    Lit le champ 'plan' dans gabriel_users (Supabase), sinon fallback users.json.
    Par défaut : 'free'.
    """
    if not user_id:
        return 'free'
    if _supabase:
        try:
            res = _supabase.table(_T_USERS).select('plan').eq('user_id', user_id).limit(1).execute()
            rows = res.data or []
            if rows:
                return rows[0].get('plan') or 'free'
        except Exception as e:
            print(f'[DB] get_user_plan error: {e}')
    # Fallback : lire users.json local
    users_file = os.path.join(_DATA_DIR, 'users.json')
    if os.path.exists(users_file):
        try:
            with open(users_file, 'r', encoding='utf-8') as f:
                users = json.load(f)
            user = users.get(user_id, {})
            return user.get('plan', 'free')
        except Exception:
            pass
    return 'free'


def count_user_analyses(user_id):
    """
    Retourne le nombre total d'analyses de l'utilisateur (pas de limite mensuelle — total lifetime).
    Utilisé pour bloquer après FREE_ANALYSES_LIMIT sur le plan gratuit.
    """
    if not user_id:
        return 0
    if _supabase:
        try:
            res = (
                _supabase.table(_T_ANALYSES)
                .select('analysis_id', count='exact')
                .eq('user_id', user_id)
                .execute()
            )
            return res.count or len(res.data or [])
        except Exception as e:
            print(f'[DB] count_user_analyses error: {e}')
    # Fallback JSON
    return sum(1 for e in _load_json_history()
               if e.get('user_id') == user_id or not e.get('user_id'))


def check_usage_limit(user_id, email=None):
    """
    Vérifie si l'utilisateur peut encore lancer une analyse.
    Retourne un dict :
      {'allowed': True}  — peut analyser
      {'allowed': False, 'reason': 'limit', 'used': N, 'limit': 5, 'plan': 'free'}
    """
    # Bypass admin by stable internal identity only.
    # ``email`` is retained for call compatibility only. It never grants a
    # privilege: only the stable internal user UUID can do so.
    if is_admin_user_id(user_id):
        return {'allowed': True, 'plan': 'admin', 'used': 0, 'limit': 999}

    # En mode dev (AUTH_ENABLED=false), pas de limite
    if os.environ.get('AUTH_ENABLED', 'false').lower() != 'true':
        return {'allowed': True, 'plan': 'dev', 'used': 0, 'limit': 999}

    plan = get_user_plan(user_id)
    if plan and plan != 'free':
        return {'allowed': True, 'plan': plan}

    used  = count_user_analyses(user_id)
    limit = FREE_ANALYSES_LIMIT
    if used >= limit:
        return {
            'allowed': False,
            'reason':  'limit',
            'used':    used,
            'limit':   limit,
            'plan':    'free',
        }
    return {'allowed': True, 'plan': 'free', 'used': used, 'limit': limit}


def upgrade_user_plan(user_id, plan):
    """Met à jour le plan d'un utilisateur (appelé par le webhook Stripe)."""
    if not user_id or not plan:
        return False
    if _supabase:
        try:
            _supabase.table(_T_USERS).update({'plan': plan}).eq('user_id', user_id).execute()
            return True
        except Exception as e:
            print(f'[DB] upgrade_user_plan error: {e}')
    # Fallback JSON
    users_file = os.path.join(_DATA_DIR, 'users.json')
    if os.path.exists(users_file):
        try:
            with open(users_file, 'r', encoding='utf-8') as f:
                users = json.load(f)
            if user_id in users:
                users[user_id]['plan'] = plan
                with open(users_file, 'w', encoding='utf-8') as f:
                    json.dump(users, f, ensure_ascii=False, indent=2)
                return True
        except Exception:
            pass
    return False


# ─────────────────────────────────────────────────────────────────────────────
# CRÉDITS — solde partagé entre les 3 agents (Psychologue/Stratège/Créateur)
#
# 300 crédits offerts à l'inscription (voir gabriel_users.credits, DEFAULT 300
# côté Supabase — supabase/credits_migration.sql). Indépendant de
# FREE_ANALYSES_LIMIT ci-dessus (qui reste actif tel quel, cf. tests
# existants) : les crédits sont la limite transversale, l'ancien compteur
# reste une limite spécifique au Psychologue.
# ─────────────────────────────────────────────────────────────────────────────

DEFAULT_FREE_CREDITS = 300


class CreditError(RuntimeError):
    """Base class for credit failures that must stop a paid operation."""


class CreditStoreUnavailable(CreditError):
    """The configured credit store could not be read."""


class CreditAccountNotFound(CreditError):
    """No persisted account exists for this user id."""


class CreditBalanceMissing(CreditError):
    """The account exists but has no usable persisted credit balance."""


class CreditDeductionFailed(CreditError):
    """A debit could not be confirmed by the persistent store."""

# Le Psychologue coûte le plus cher (scraping + analyse profonde d'audience),
# le Créateur le moins cher (il exécute une décision déjà construite par les
# deux agents précédents, pas de travail d'analyse).
CREDIT_COSTS = {
    'psychologue': 80,
    'stratege':    50,
    'createur':    20,
}


def get_user_credits(user_id):
    """Return the persisted balance; never invent credits after a read error.

    The initial 300 credits are assigned by account creation (the SQL column
    default in Supabase, or the explicit value in ``users.json``), not here.
    """
    if not user_id:
        return 0
    if _supabase:
        try:
            res = _supabase.table(_T_USERS).select('credits').eq('user_id', user_id).limit(1).execute()
            rows = res.data or []
        except Exception as e:
            print(f'[DB] get_user_credits unavailable: {type(e).__name__}')
            raise CreditStoreUnavailable('credit store read failed') from e
        if not rows:
            raise CreditAccountNotFound('credit account not found')
        try:
            credits = rows[0].get('credits')
        except (AttributeError, TypeError) as e:
            raise CreditBalanceMissing('credit balance invalid') from e
        if credits is None:
            raise CreditBalanceMissing('credit balance missing')
        try:
            balance = int(credits)
        except (TypeError, ValueError) as e:
            raise CreditBalanceMissing('credit balance invalid') from e
        if balance < 0:
            raise CreditBalanceMissing('credit balance invalid')
        return balance

    users_file = os.path.join(_DATA_DIR, 'users.json')
    if not os.path.exists(users_file):
        raise CreditAccountNotFound('credit account not found')
    try:
        with open(users_file, 'r', encoding='utf-8') as f:
            users = json.load(f)
    except (OSError, ValueError, TypeError) as e:
        print(f'[DB] get_user_credits local unavailable: {type(e).__name__}')
        raise CreditStoreUnavailable('local credit store read failed') from e

    # Historical Google fallback files are keyed by google_id, not user_id.
    # Locate by the persisted field too so legitimate accounts keep their
    # signup balance and can actually be debited.
    user = users.get(user_id)
    if not isinstance(user, dict) or str(user.get('user_id')) != str(user_id):
        user = next(
            (row for row in users.values()
             if isinstance(row, dict) and str(row.get('user_id')) == str(user_id)),
            None,
        )
    if not user:
        raise CreditAccountNotFound('credit account not found')
    credits = user.get('credits')
    if credits is None:
        raise CreditBalanceMissing('credit balance missing')
    try:
        balance = int(credits)
    except (TypeError, ValueError) as e:
        raise CreditBalanceMissing('credit balance invalid') from e
    if balance < 0:
        raise CreditBalanceMissing('credit balance invalid')
    return balance


def has_enough_credits(user_id, cost, email=None):
    """Vérifie le solde avant de lancer un agent.

    Admin/dev restent exemptés du seuil, mais seulement après une lecture
    réussie : une panne du stockage ne doit jamais autoriser un coût payant.
    """
    if not user_id:
        return True
    balance = get_user_credits(user_id)
    if is_admin_user_id(user_id):
        return True
    if os.environ.get('AUTH_ENABLED', 'false').lower() != 'true':
        return True
    return balance >= cost


def deduct_credits(user_id, cost, reason=''):
    """Débite `cost` crédits après un usage réussi d'un agent (jamais avant —
    un échec ne doit pas coûter de crédits). Ne descend jamais sous zéro.
    Retourne le nouveau solde."""
    if not user_id or cost <= 0:
        return get_user_credits(user_id)
    new_balance = max(0, get_user_credits(user_id) - cost)
    if _supabase:
        try:
            res = _supabase.table(_T_USERS).update({'credits': new_balance}).eq('user_id', user_id).execute()
            rows = res.data or []
        except Exception as e:
            print(f'[DB] deduct_credits failed: {type(e).__name__}')
            raise CreditDeductionFailed('credit debit write failed') from e
        if not rows:
            raise CreditDeductionFailed('credit debit updated no account')
        try:
            persisted_balance = int(rows[0].get('credits'))
        except (AttributeError, TypeError, ValueError) as e:
            raise CreditDeductionFailed('credit debit response invalid') from e
        if persisted_balance != new_balance:
            raise CreditDeductionFailed('credit debit was not persisted')
    else:
        users_file = os.path.join(_DATA_DIR, 'users.json')
        try:
            with open(users_file, 'r', encoding='utf-8') as f:
                users = json.load(f)
            storage_key = next(
                (key for key, row in users.items()
                 if isinstance(row, dict) and str(row.get('user_id')) == str(user_id)),
                None,
            )
            if storage_key is None:
                raise CreditAccountNotFound('credit account not found')
            users[storage_key]['credits'] = new_balance
            with open(users_file, 'w', encoding='utf-8') as f:
                json.dump(users, f, ensure_ascii=False, indent=2)
        except CreditError:
            raise
        except (OSError, ValueError, TypeError) as e:
            print(f'[DB] deduct_credits local failed: {type(e).__name__}')
            raise CreditDeductionFailed('local credit debit write failed') from e
    print(f'[CREDITS] user={user_id} -{cost} ({reason}) -> {new_balance}')
    return new_balance


# ─────────────────────────────────────────────────────────────────────────────
# EXPORTS
# ─────────────────────────────────────────────────────────────────────────────

def save_export(user_id, export_type='pdf', full_text='', extra=None,
                analysis_id=None, strategy_id=None, pdf_path=None):
    """Sauvegarde un export (PDF ou contenu créateur) dans Supabase.

    `extra` va dans la colonne `metadata` (jsonb) — jamais éclaté en colonnes
    top-level. Trouvé en conditions réelles : gabriel_exports n'a pas de
    colonne `channel` (ni `content_type`/`tone`/`content_json`), donc chaque
    sauvegarde du Créateur échouait sur Supabase (PGRST204) et retombait
    silencieusement sur un fichier JSON local — perdu à chaque redéploiement
    sur Render (disque éphémère). L'utilisateur voyait "✓ Sauvegardé" alors
    que rien n'était réellement conservé."""
    if not user_id:
        return None

    row = {
        'user_id':     user_id,
        'analysis_id': analysis_id or '',
        'strategy_id': strategy_id or '',
        'export_type': export_type,
        'pdf_path':    pdf_path or '',
        'full_text':   full_text[:10000] if full_text else '',
        'created_at':  datetime.datetime.utcnow().isoformat(),
    }
    if extra and isinstance(extra, dict):
        row['metadata'] = extra

    if _supabase:
        try:
            res = _supabase.table(_T_EXPORTS).insert(row).execute()
            return (res.data or [{}])[0]
        except Exception as e:
            print(f'[DB] save_export error: {e}')

    # Fallback JSON local
    _exports_file = os.path.join(_DATA_DIR, 'exports.json')
    try:
        exports = []
        if os.path.exists(_exports_file):
            with open(_exports_file, 'r', encoding='utf-8') as f:
                exports = json.load(f)
        row['id'] = str(uuid.uuid4())
        exports.append(row)
        os.makedirs(_DATA_DIR, exist_ok=True)
        with open(_exports_file, 'w', encoding='utf-8') as f:
            json.dump(exports[-200:], f, ensure_ascii=False, indent=2)
        return row
    except Exception as e:
        print(f'[DB] save_export fallback error: {e}')
    return None


def get_exports(user_id, limit=50):
    """Retourne les exports d'un utilisateur (PDF + contenus créateur)."""
    if _supabase and user_id:
        try:
            res = (_supabase.table(_T_EXPORTS)
                   .select('*').eq('user_id', user_id)
                   .order('created_at', desc=True).limit(limit).execute())
            return res.data or []
        except Exception as e:
            print(f'[DB] get_exports error: {e}')

    # Fallback JSON local
    _exports_file = os.path.join(_DATA_DIR, 'exports.json')
    if os.path.exists(_exports_file):
        try:
            with open(_exports_file, 'r', encoding='utf-8') as f:
                all_exp = json.load(f)
            if user_id:
                all_exp = [e for e in all_exp if e.get('user_id') == user_id]
            return sorted(all_exp, key=lambda x: x.get('created_at',''), reverse=True)[:limit]
        except Exception:
            pass
    return []


# ─────────────────────────────────────────────────────────────────────────────
# JSON FALLBACK (développement / offline)
# ─────────────────────────────────────────────────────────────────────────────

def _load_json_history():
    if os.path.exists(_HISTORY_FILE):
        try:
            with open(_HISTORY_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    return []


def _write_json_history(history):
    os.makedirs(_DATA_DIR, exist_ok=True)
    with open(_HISTORY_FILE, 'w', encoding='utf-8') as f:
        json.dump(history, f, ensure_ascii=False, indent=2)


def _save_json_entry(entry):
    """Sauvegarde / met à jour une entrée dans le fallback JSON."""
    history = _load_json_history()
    aid = entry.get('analysis_id')
    history = [e for e in history if e.get('analysis_id') != aid]
    history.insert(0, entry)
    history = history[:100]
    _write_json_history(history)


# ── Stratégies (fallback JSON) ────────────────────────────────────────────────

def _load_json_strategies():
    if os.path.exists(_STRATEGIES_FILE):
        try:
            with open(_STRATEGIES_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    return []


def _write_json_strategies(rows):
    os.makedirs(_DATA_DIR, exist_ok=True)
    with open(_STRATEGIES_FILE, 'w', encoding='utf-8') as f:
        json.dump(rows, f, ensure_ascii=False, indent=2)


# ── Feedbacks (fallback JSON) ─────────────────────────────────────────────────

def _load_json_feedbacks():
    if os.path.exists(_FEEDBACKS_FILE):
        try:
            with open(_FEEDBACKS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    return []


def _write_json_feedbacks(rows):
    os.makedirs(_DATA_DIR, exist_ok=True)
    with open(_FEEDBACKS_FILE, 'w', encoding='utf-8') as f:
        json.dump(rows, f, ensure_ascii=False, indent=2)


# ── Survey events ─────────────────────────────────────────────────────────────

def save_survey_event(user_id: str, event_type: str, target_type: str = '',
                      target_id: str = '', metadata: dict = None) -> str:
    """Enregistre qu'une enquête a été affichée. Retourne l'event_id."""
    event_id = str(uuid.uuid4())
    row = {
        'id':          event_id,
        'user_id':     user_id,
        'event_type':  event_type,
        'target_type': target_type or '',
        'target_id':   target_id or '',
        'status':      'shown',
        'metadata':    metadata or {},
    }
    if _supabase:
        try:
            _supabase.table(_T_SURVEY_EVT).insert(row).execute()
        except Exception as e:
            print(f'[DB] save_survey_event error: {e}')
    return event_id


def update_survey_event_status(event_id: str, user_id: str, status: str) -> bool:
    """Met à jour le statut d'un événement enquête (responded / dismissed / later)."""
    if not _supabase:
        return True
    import datetime as _dt
    ts = _dt.datetime.utcnow().isoformat()
    patch = {'status': status}
    if status == 'responded':
        patch['responded_at'] = ts
    elif status in ('dismissed', 'later'):
        patch['dismissed_at'] = ts
    try:
        _supabase.table(_T_SURVEY_EVT)\
            .update(patch)\
            .eq('id', event_id)\
            .eq('user_id', user_id)\
            .execute()
        return True
    except Exception as e:
        print(f'[DB] update_survey_event_status error: {e}')
        return False


# ── Survey responses ──────────────────────────────────────────────────────────

def save_survey_response(user_id: str, response: dict) -> bool:
    """Enregistre la réponse complète d'un utilisateur à une enquête."""
    def _clamp(v):
        try:
            n = int(v)
            return n if 1 <= n <= 5 else None
        except (TypeError, ValueError):
            return None

    row = {
        'user_id':             user_id,
        'survey_event_id':     str(response.get('survey_event_id') or ''),
        'target_type':         str(response.get('target_type') or '')[:50],
        'target_id':           str(response.get('target_id') or '')[:255],
        'agent':               str(response.get('agent') or '')[:50],
        'quick_answer':        str(response.get('quick_answer') or '')[:20],
        'relevance_score':     _clamp(response.get('relevance_score')),
        'clarity_score':       _clamp(response.get('clarity_score')),
        'usefulness_score':    _clamp(response.get('usefulness_score')),
        'actionability_score': _clamp(response.get('actionability_score')),
        'free_feedback':       str(response.get('free_feedback') or '')[:2000],
    }
    # Retirer les champs None (scores optionnels)
    row = {k: v for k, v in row.items() if v is not None}

    if _supabase:
        try:
            _supabase.table(_T_SURVEY_RESP).insert(row).execute()
        except Exception as e:
            print(f'[DB] save_survey_response error: {e}')
    return True  # fallback local : toujours OK


# ── Consentement ──────────────────────────────────────────────────────────────

def save_consent(user_id: str, consent_type: str, status: str, source: str = '') -> bool:
    """Enregistre ou met à jour un consentement utilisateur."""
    import datetime as _dt
    row = {
        'user_id':      user_id,
        'consent_type': consent_type,
        'status':       status,
        'source':       source or '',
        'withdrawn_at': _dt.datetime.utcnow().isoformat() if status == 'withdrawn' else None,
    }
    row = {k: v for k, v in row.items() if v is not None}
    if _supabase:
        try:
            _supabase.table(_T_CONSENT).insert(row).execute()
        except Exception as e:
            print(f'[DB] save_consent error: {e}')
    return True  # fallback local : toujours OK


def get_consent(user_id: str, consent_type: str) -> str:
    """Retourne le statut du consentement le plus récent ('granted'|'withdrawn'|'unknown')."""
    if _supabase:
        try:
            res = (
                _supabase.table(_T_CONSENT)
                .select('status')
                .eq('user_id', user_id)
                .eq('consent_type', consent_type)
                .order('created_at', desc=True)
                .limit(1)
                .execute()
            )
            if res.data:
                return res.data[0].get('status', 'unknown')
        except Exception as e:
            print(f'[DB] get_consent error: {e}')
    return 'unknown'


# ─────────────────────────────────────────────────────────────────────────────
# DOSSIERS STRATÉGIQUES
# ─────────────────────────────────────────────────────────────────────────────

def create_folder(folder_id, user_id, title, objective='', folder_type='audience'):
    """Crée un dossier stratégique. Retourne le dict créé ou None."""
    if not (user_id and title and title.strip()):
        return None
    now = datetime.datetime.utcnow().isoformat()
    row = {
        'folder_id':   folder_id,
        'user_id':     user_id,
        'title':       str(title).strip()[:200],
        'objective':   str(objective or '').strip()[:500],
        'folder_type': folder_type or 'audience',
        'status':      'active',
        'step':        'source',
        'created_at':  now,
        'updated_at':  now,
    }
    persisted = False
    if _supabase:
        try:
            _supabase.table(_T_FOLDERS).insert(row).execute()
            persisted = True
        except Exception as e:
            print(f'[DB] create_folder error: {e}')
            return None
    if persisted:
        _cache_folder(user_id, row)
    return row


def get_folders(user_id, limit=50):
    """Liste les dossiers d'un utilisateur (métadonnées seulement)."""
    if not user_id:
        return []
    if _supabase:
        try:
            res = (
                _supabase.table(_T_FOLDERS)
                .select('folder_id,title,objective,folder_type,status,step,analysis_id,cross_analysis_id,strategy_id,creator_output_id,source_type,source_summary,created_at,updated_at')
                .eq('user_id', user_id)
                .order('updated_at', desc=True)
                .limit(limit)
                .execute()
            )
            rows = res.data or []
            for row in rows:
                _cache_folder(user_id, row)
            return rows
        except Exception as e:
            print(f'[DB] get_folders error: {e}')
            # Supabase est indisponible : conserver l'espace déjà visible au
            # lieu de le faire disparaître. Les entrées restent cloisonnées par
            # user_id et seront réconciliées à la prochaine lecture réussie.
            return _cached_folders(user_id, limit)
    return _cached_folders(user_id, limit)


def get_folder_by_id(folder_id, user_id):
    """Retourne un dossier complet. None si introuvable ou appartient à un autre user."""
    if not (folder_id and user_id):
        return None
    if _supabase:
        try:
            res = (
                _supabase.table(_T_FOLDERS)
                .select('*')
                .eq('folder_id', folder_id)
                .eq('user_id', user_id)
                .limit(1)
                .execute()
            )
            rows = res.data or []
            if rows:
                _cache_folder(user_id, rows[0])
                return rows[0]
            # Une réponse valide mais vide confirme que le dossier n'existe
            # plus : ne pas conserver une copie périmée dans ce cas précis.
            _folder_cache.pop((str(user_id), str(folder_id)), None)
            return None
        except Exception as e:
            print(f'[DB] get_folder_by_id error: {e}')
            return _cached_folder(folder_id, user_id)
    return _cached_folder(folder_id, user_id)


def update_folder(folder_id, user_id, **fields):
    """Met à jour les champs d'un dossier. Retourne True si succès."""
    if not (folder_id and user_id):
        return False
    allowed = {'title', 'objective', 'folder_type', 'status', 'step',
               'analysis_id', 'cross_analysis_id', 'strategy_id', 'creator_output_id',
               'source_type', 'source_summary'}
    payload = {k: v for k, v in fields.items() if k in allowed}
    if not payload:
        return False
    payload['updated_at'] = datetime.datetime.utcnow().isoformat()
    if _supabase:
        try:
            _supabase.table(_T_FOLDERS)\
                .update(payload)\
                .eq('folder_id', folder_id)\
                .eq('user_id', user_id)\
                .execute()
            cached = _cached_folder(folder_id, user_id) or {
                'folder_id': folder_id,
                'user_id': user_id,
            }
            cached.update(payload)
            _cache_folder(user_id, cached)
            return True
        except Exception as e:
            print(f'[DB] update_folder error: {e}')
    return False


def delete_folder(folder_id, user_id):
    """Supprime un dossier (lien seulement — les analyses sous-jacentes restent). Retourne True si succès."""
    if not (folder_id and user_id):
        return False
    if _supabase:
        try:
            _supabase.table(_T_FOLDERS)\
                .delete()\
                .eq('folder_id', folder_id)\
                .eq('user_id', user_id)\
                .execute()
            _folder_cache.pop((str(user_id), str(folder_id)), None)
            return True
        except Exception as e:
            print(f'[DB] delete_folder error: {e}')
    return False


# ─────────────────────────────────────────────────────────────────────────────
# CONTEXT BUILDER ARCHITECTURE — V1.1 : Business Context Store
#
# Barrière de sécurité réelle : la clé Supabase utilisée ici (sb_secret_...)
# contourne RLS par conception (voir supabase/context_builder_migration.sql).
# CHAQUE fonction ci-dessous DOIT filtrer par user_id — c'est la seule
# protection effective contre l'accès aux données d'un autre utilisateur.
# ─────────────────────────────────────────────────────────────────────────────

def create_context_session(session_id, user_id, folder_id=''):
    """Crée une session de conversation Context Builder. Retourne True si succès."""
    if not (_supabase and session_id and user_id):
        return False
    try:
        row = {
            'session_id': session_id,
            'user_id':    user_id,
            'folder_id':  folder_id or '',
            'status':     'active',
        }
        _supabase.table(_T_CTX_SESSIONS).insert(row).execute()
        return True
    except Exception as e:
        print(f'[DB] create_context_session error: {e}')
        return False


def get_active_context_session(user_id):
    """Retourne la session active la plus récente de l'utilisateur, ou None.
    Permet la reprise de session : rouvrir la page continue là où on s'était arrêté."""
    if not (_supabase and user_id):
        return None
    try:
        res = (
            _supabase.table(_T_CTX_SESSIONS)
            .select('*')
            .eq('user_id', user_id)
            .eq('status', 'active')
            .order('updated_at', desc=True)
            .limit(1)
            .execute()
        )
        rows = res.data or []
        return rows[0] if rows else None
    except Exception as e:
        print(f'[DB] get_active_context_session error: {e}')
        return None


def update_context_session(session_id, user_id, **fields):
    """Met à jour une session (status, current_dimension, current_step...).
    Retourne True si succès."""
    if not (_supabase and session_id and user_id):
        return False
    allowed = {'status', 'current_dimension', 'folder_id', 'completed_at', 'current_step'}
    payload = {k: v for k, v in fields.items() if k in allowed}
    if not payload:
        return False
    payload['updated_at'] = datetime.datetime.utcnow().isoformat()
    try:
        _supabase.table(_T_CTX_SESSIONS)\
            .update(payload)\
            .eq('session_id', session_id)\
            .eq('user_id', user_id)\
            .execute()
        return True
    except Exception as e:
        print(f'[DB] update_context_session error: {e}')
        return False


# Rappel unique en cas de base pas encore migrée : sans ce garde-fou, chaque
# changement d'étape écrirait la même erreur dans les journaux.
_step_column_warned = False


def set_session_step(session_id, user_id, step):
    """Enregistre l'étape du PARCOURS (welcome, interview...) — distincte de
    `current_dimension`, qui suit l'avancement à l'intérieur de l'entretien.

    Tolère une base pas encore migrée : tant que la colonne `current_step`
    n'existe pas (voir supabase/strategy_session_migration.sql), l'écriture
    échoue silencieusement et le parcours fonctionne quand même — il repart
    simplement à l'accueil au rechargement plutôt que de reprendre où il en
    était. Le produit reste utilisable pendant le déploiement de la
    migration, au lieu de tomber en panne en attendant.
    """
    global _step_column_warned
    if not (_supabase and session_id and user_id and step):
        return False
    ok = update_context_session(session_id, user_id, current_step=step)
    if not ok and not _step_column_warned:
        _step_column_warned = True
        print('[DB] colonne current_step absente — exécuter '
              'supabase/strategy_session_migration.sql pour activer la '
              'reprise du parcours à l\'étape en cours.')
    return ok


def save_context_message(session_id, user_id, role, content, dimension_key=''):
    """Enregistre un message de la conversation (pour la reprise de session)."""
    if not (_supabase and session_id and user_id and role and content):
        return False
    try:
        row = {
            'session_id':    session_id,
            'user_id':       user_id,
            'role':          role,
            'content':       content,
            'dimension_key': dimension_key or '',
        }
        _supabase.table(_T_CTX_MESSAGES).insert(row).execute()
        return True
    except Exception as e:
        print(f'[DB] save_context_message error: {e}')
        return False


def get_context_messages(session_id, user_id, limit=200):
    """Historique des messages d'une session, dans l'ordre chronologique."""
    if not (_supabase and session_id and user_id):
        return []
    try:
        res = (
            _supabase.table(_T_CTX_MESSAGES)
            .select('*')
            .eq('session_id', session_id)
            .eq('user_id', user_id)
            .order('created_at')
            .limit(limit)
            .execute()
        )
        return res.data or []
    except Exception as e:
        print(f'[DB] get_context_messages error: {e}')
        return []


def get_context_fields(user_id):
    """Retourne tous les champs du contexte business de l'utilisateur,
    sous forme de dict {field_key: value} — la vue consommée par le Stratège."""
    if not (_supabase and user_id):
        return {}
    try:
        res = (
            _supabase.table(_T_CTX_FIELDS)
            .select('*')
            .eq('user_id', user_id)
            .execute()
        )
        rows = res.data or []
        return {r['field_key']: r['value'] for r in rows if r.get('field_key')}
    except Exception as e:
        print(f'[DB] get_context_fields error: {e}')
        return {}


def get_context_fields_full(user_id):
    """Comme get_context_fields, mais retourne les lignes complètes
    (status, confidence, source_session_id...) — utile pour l'affichage
    de la complétude et la traçabilité des sources."""
    if not (_supabase and user_id):
        return []
    try:
        res = (
            _supabase.table(_T_CTX_FIELDS)
            .select('*')
            .eq('user_id', user_id)
            .execute()
        )
        return res.data or []
    except Exception as e:
        print(f'[DB] get_context_fields_full error: {e}')
        return []


def delete_context_fields(user_id):
    """Efface tous les champs du contexte business d'un utilisateur — réservé
    à une action explicitement confirmée par l'utilisateur (reset)."""
    if not (_supabase and user_id):
        return False
    try:
        _supabase.table(_T_CTX_FIELDS).delete().eq('user_id', user_id).execute()
        return True
    except Exception as e:
        print(f'[DB] delete_context_fields error: {e}')
        return False


def upsert_context_field(user_id, field_key, value, status='extracted',
                          confidence=1.0, source_session_id=''):
    """Insère ou met à jour un champ du contexte business (une valeur par
    field_key et par utilisateur — contrainte UNIQUE(user_id, field_key))."""
    if not (_supabase and user_id and field_key):
        return False
    try:
        now = datetime.datetime.utcnow().isoformat()
        row = {
            'user_id':           user_id,
            'field_key':         field_key,
            'value':             str(value)[:5000],
            'status':            status,
            'confidence':        confidence,
            'source_session_id': source_session_id or '',
            'updated_at':        now,
        }
        _supabase.table(_T_CTX_FIELDS)\
            .upsert(row, on_conflict='user_id,field_key')\
            .execute()
        return True
    except Exception as e:
        print(f'[DB] upsert_context_field error: {e}')
        return False


# ─────────────────────────────────────────────────────────────────────────────
# SUPPRESSION DE COMPTE — purge complète, table par table
# ─────────────────────────────────────────────────────────────────────────────

# Toutes les tables Supabase indexées par user_id, y compris les tables de
# conformité (consentements, événements d'enquête) — suppression complète et
# immédiate demandée explicitement, pas de conservation ni d'anonymisation.
_ACCOUNT_DATA_TABLES = [
    _T_FOLDERS, _T_JOBS, _T_CROSS_SOURCES, _T_SOURCE_COMMENTS,
    _T_PSYCHO_SOURCES, _T_CROSS_ANALYSES, _T_ANALYSES, _T_STRATEGIES, _T_EXPORTS,
    _T_FEEDBACKS, _T_SURVEY_EVT, _T_SURVEY_RESP, _T_CONSENT,
    _T_CHAT_CONV, _T_CHAT_MSG, _T_TRAIN_CAND,
    _T_CTX_SESSIONS, _T_CTX_MESSAGES, _T_CTX_FIELDS, _T_MEMORY_CASES,
]


def delete_all_user_data(user_id):
    """
    Purge complète des données Supabase d'un utilisateur (suppression de compte).
    Best-effort : une table qui échoue n'empêche pas les suivantes. Retourne la
    liste des tables qui ont échoué (vide = tout est passé).
    """
    if not user_id:
        return ['invalid_user_id']
    failed = []
    if _supabase:
        for table in _ACCOUNT_DATA_TABLES:
            try:
                _supabase.table(table).delete().eq('user_id', user_id).execute()
            except Exception as e:
                print(f'[DB] delete_all_user_data error on {table}: {e}')
                failed.append(table)
        # La ligne du compte lui-même, en dernier
        try:
            _supabase.table(_T_USERS).delete().eq('user_id', user_id).execute()
        except Exception as e:
            print(f'[DB] delete_all_user_data error on {_T_USERS}: {e}')
            failed.append(_T_USERS)
    return failed


# ─────────────────────────────────────────────────────────────────────────────
# MÉMOIRE DE CAS DU STRATÈGE (core/memory.py)
#
# gabriel_memory_cases (voir supabase/memory_cases_migration.sql) remplace
# l'ancien stockage en fichier JSON local, effacé à chaque déploiement Render.
# ─────────────────────────────────────────────────────────────────────────────

GLOBAL_MEMORY_POOL_LIMIT = 300


def memory_shared_across_users():
    """La mémoire de cas est cloisonnée par compte par défaut.

    Ces cas contiennent l'offre, le prix et la décision stratégique de chaque
    utilisateur : les montrer dans le prompt d'un autre compte contredit la
    promesse d'isolation du protocole bêta (audit du 24/09/2026). Le
    partage global se réactive explicitement (MEMORY_SHARE_ACROSS_USERS=true)
    pour un usage où tous les comptes appartiennent à la même équipe."""
    return os.environ.get('MEMORY_SHARE_ACROSS_USERS', 'false').lower() == 'true'


def get_memory_cases(user_id=None):
    """Pool de cas pour la recherche de similarité : tout l'historique de cet
    utilisateur + un échantillon récent tous comptes confondus, pour que les
    patterns détectés s'appuient sur plus que ses seuls cas (apprentissage
    global — voir core/memory.py find_similar, qui priorise déjà les cas de
    l'utilisateur quand il en a assez avant de retomber sur ce pool élargi)."""
    if not _supabase:
        return []
    shared = memory_shared_across_users()
    if not user_id and not shared:
        return []          # jamais un vidage de tous les comptes vers un processus sans utilisateur
    cases, seen = [], set()
    try:
        if user_id:
            res = (
                _supabase.table(_T_MEMORY_CASES).select('*')
                .eq('user_id', user_id).order('created_at', desc=True).execute()
            )
            for row in (res.data or []):
                cases.append(row)
                seen.add(row['case_id'])
    except Exception as e:
        print(f'[DB] get_memory_cases (user) error: {e}')
    if not shared:
        return cases
    try:
        res = (
            _supabase.table(_T_MEMORY_CASES).select('*')
            .order('created_at', desc=True).limit(GLOBAL_MEMORY_POOL_LIMIT).execute()
        )
        for row in (res.data or []):
            if row['case_id'] not in seen:
                cases.append(row)
                seen.add(row['case_id'])
    except Exception as e:
        print(f'[DB] get_memory_cases (global) error: {e}')
    return cases


def upsert_memory_case(case_row):
    """Écrit un cas (un par analyse — voir la contrainte unique sur case_id)."""
    if not (_supabase and case_row.get('case_id') and case_row.get('user_id')):
        return False
    try:
        _supabase.table(_T_MEMORY_CASES).upsert(case_row, on_conflict='case_id').execute()
        return True
    except Exception as e:
        print(f'[DB] upsert_memory_case error: {e}')
        return False


def update_memory_case_field(case_id, field, value):
    """Met à jour un seul champ (feedback, satisfaction ou performance) d'un
    cas déjà enregistré, sans re-écrire tout le reste."""
    if not (_supabase and case_id and field):
        return False
    try:
        res = (
            _supabase.table(_T_MEMORY_CASES)
            .update({field: value, 'updated_at': datetime.datetime.now().isoformat()})
            .eq('case_id', case_id).execute()
        )
        return bool(res.data)
    except Exception as e:
        print(f'[DB] update_memory_case_field error: {e}')
        return False
