# ─── Gabriel — Data Access Layer (Supabase + JSON fallback) ──────────────────
#
# Tables Supabase : gabriel_analyses, gabriel_strategies, gabriel_feedbacks, gabriel_exports,
#                   gabriel_survey_events, gabriel_survey_responses, gabriel_consent_records,
#                   gabriel_chat_conversations, gabriel_chat_messages, gabriel_training_candidates
# Fallback       : data/history.json (développement local)
# Accès         : UUID/analysis_id — jamais par index entier

import os
import json
import uuid
import datetime

_BASE_DIR     = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DATA_DIR     = os.path.join(_BASE_DIR, 'data')
_HISTORY_FILE    = os.path.join(_DATA_DIR, 'history.json')
_STRATEGIES_FILE = os.path.join(_DATA_DIR, 'strategies.json')
_FEEDBACKS_FILE  = os.path.join(_DATA_DIR, 'feedbacks.json')

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

FREE_ANALYSES_LIMIT = 3

# Emails avec accès illimité (admin / fondateurs)
ADMIN_EMAILS = frozenset({'outilsagencechretienne@gmail.com'})

_supabase = None


def init_db(client):
    global _supabase
    _supabase = client


# ─────────────────────────────────────────────────────────────────────────────
# ANALYSES
# ─────────────────────────────────────────────────────────────────────────────

def get_history(user_id=None, limit=50):
    """Liste des analyses (métadonnées only, pas le full_result)."""
    if _supabase and user_id:
        try:
            res = (
                _supabase.table(_T_ANALYSES)
                .select('analysis_id,title,source,nb_commentaires,created_at,has_strategy')
                .eq('user_id', user_id)
                .order('created_at', desc=True)
                .limit(limit)
                .execute()
            )
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
        for e in history
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
        except Exception as e:
            print(f'[DB] save_analysis Supabase error: {e}')

    # Toujours sauvegarder en local (fallback)
    _save_json_entry(entry)


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
        except Exception as e:
            print(f'[DB] update_analysis_strategy error: {e}')

    # Fallback JSON
    history = _load_json_history()
    for e in history:
        if e.get('analysis_id') == analysis_id:
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
    history = [e for e in history if e.get('analysis_id') != analysis_id]
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
        except Exception as e:
            print(f'[DB] save_strategy Supabase error: {e}')

    # Fallback JSON — toujours, pour que la stratégie survive à la navigation (dev + offline)
    try:
        rows = _load_json_strategies()
        rows = [r for r in rows if r.get('strategy_id') != strategy_id]
        rows.insert(0, {
            'user_id':          user_id or 'local',
            'strategy_id':      strategy_id,
            'analysis_id':      analysis_id or '',
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


def get_strategies(user_id=None, limit=50):
    """Liste des stratégies de l'utilisateur (métadonnées + statut feedback)."""
    fb_index = _feedback_index(user_id)

    if _supabase and user_id:
        try:
            res = (
                _supabase.table(_T_STRATEGIES)
                .select('strategy_id,analysis_id,strategy_result,created_at')
                .eq('user_id', user_id)
                .order('created_at', desc=True)
                .limit(limit)
                .execute()
            )
            return [_attach_feedback({
                'strategy_id': r.get('strategy_id'),
                'analysis_id': r.get('analysis_id', ''),
                'title':       _strategy_title(r.get('strategy_result') or {}),
                'created_at':  r.get('created_at', ''),
            }, fb_index) for r in (res.data or [])]
        except Exception as e:
            print(f'[DB] get_strategies error: {e}')

    # Fallback JSON
    rows = _load_json_strategies()
    return [_attach_feedback({
        'strategy_id': r.get('strategy_id'),
        'analysis_id': r.get('analysis_id', ''),
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
                    'title':            _strategy_title(r.get('strategy_result') or {}),
                    'business_context': r.get('business_context') or {},
                    'strategy_result':  r.get('strategy_result') or {},
                    'created_at':       r.get('created_at', ''),
                }
        except Exception as e:
            print(f'[DB] get_strategy_by_id error: {e}')

    # Fallback JSON
    for r in _load_json_strategies():
        if r.get('strategy_id') == strategy_id:
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
    new_rows = [r for r in rows if r.get('strategy_id') != strategy_id]
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

    # Fallback JSON — toujours
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

    return _load_json_feedbacks()[:limit]


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
    Retourne le plan de l'utilisateur : 'free' | 'starter' | 'pro'.
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
    # Bypass admin (fondateurs / emails spéciaux)
    if email and email.strip().lower() in ADMIN_EMAILS:
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
# EXPORTS
# ─────────────────────────────────────────────────────────────────────────────

def save_export(user_id, export_type='pdf', full_text='', extra=None,
                analysis_id=None, strategy_id=None, pdf_path=None):
    """Sauvegarde un export (PDF ou contenu créateur) dans Supabase."""
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
        for k, v in extra.items():
            if k not in row:
                row[k] = v

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
    if _supabase:
        try:
            _supabase.table(_T_FOLDERS).insert(row).execute()
        except Exception as e:
            print(f'[DB] create_folder error: {e}')
            return None
    return row


def get_folders(user_id, limit=50):
    """Liste les dossiers d'un utilisateur (métadonnées seulement)."""
    if not user_id:
        return []
    if _supabase:
        try:
            res = (
                _supabase.table(_T_FOLDERS)
                .select('folder_id,title,objective,folder_type,status,step,analysis_id,created_at,updated_at')
                .eq('user_id', user_id)
                .order('updated_at', desc=True)
                .limit(limit)
                .execute()
            )
            return res.data or []
        except Exception as e:
            print(f'[DB] get_folders error: {e}')
    return []


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
            return rows[0] if rows else None
        except Exception as e:
            print(f'[DB] get_folder_by_id error: {e}')
    return None


def update_folder(folder_id, user_id, **fields):
    """Met à jour les champs d'un dossier. Retourne True si succès."""
    if not (folder_id and user_id):
        return False
    allowed = {'title', 'objective', 'folder_type', 'status', 'step',
               'analysis_id', 'strategy_id', 'creator_output_id',
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
            return True
        except Exception as e:
            print(f'[DB] delete_folder error: {e}')
    return False


# ─────────────────────────────────────────────────────────────────────────────
# SUPPRESSION DE COMPTE — purge complète, table par table
# ─────────────────────────────────────────────────────────────────────────────

# Toutes les tables Supabase indexées par user_id, y compris les tables de
# conformité (consentements, événements d'enquête) — suppression complète et
# immédiate demandée explicitement, pas de conservation ni d'anonymisation.
_ACCOUNT_DATA_TABLES = [
    _T_FOLDERS, _T_JOBS, _T_ANALYSES, _T_STRATEGIES, _T_EXPORTS,
    _T_FEEDBACKS, _T_SURVEY_EVT, _T_SURVEY_RESP, _T_CONSENT,
    _T_CHAT_CONV, _T_CHAT_MSG, _T_TRAIN_CAND,
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
