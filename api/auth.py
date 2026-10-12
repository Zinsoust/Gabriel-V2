# ─── Gabriel — Authentification (Google OAuth + Email/Password) ───────────────
#
# AUTH_ENABLED=false → toutes les routes passent (dev local).
# AUTH_ENABLED=true  → auth obligatoire.
#
# Stockage : Supabase (gabriel_users) si configuré, sinon users.json local.

import os
import json
import uuid
import datetime
from functools import wraps
from flask import Blueprint, session, redirect, url_for, request, jsonify, render_template
from authlib.integrations.flask_client import OAuth
from authlib.integrations.base_client.errors import MismatchingStateError, OAuthError
from werkzeug.security import generate_password_hash, check_password_hash
from core.security import safe_log_event, rate_limit

_RL_LOGIN = os.environ.get('RATE_LIMIT_LOGIN', '10 per hour')

auth_bp = Blueprint('auth', __name__)
oauth   = OAuth()

# Slugs de plans valides pour rediriger vers /upgrade?plan=... après connexion —
# whitelist volontaire (jamais le contenu brut de la query string) pour ne
# jamais transformer ce paramètre en redirection ouverte.
_REDIRECT_PLANS = {'early_access', 'standard', 'pme'}


def _post_login_redirect(plan):
    if plan in _REDIRECT_PLANS:
        return redirect(f'/upgrade?plan={plan}')
    # L'Orchestrateur est le point d'entrée du parcours — pas "Dossiers",
    # qui n'est plus une étape obligatoire (un dossier est désormais créé
    # silencieusement en arrière-plan dès qu'un agent est utilisé).
    return redirect('/orchestrateur')

_BASE_DIR   = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_USERS_FILE = os.path.join(_BASE_DIR, 'data', 'users.json')
_TABLE      = 'gabriel_users'

_supabase      = None
_google_enabled = False

_PASSWORD_HASH_METHOD = 'pbkdf2:sha256'


# ── Initialisation ────────────────────────────────────────────────────────────

def init_auth(app):
    global _supabase, _google_enabled
    oauth.init_app(app)

    client_id     = os.environ.get('GOOGLE_CLIENT_ID')
    client_secret = os.environ.get('GOOGLE_CLIENT_SECRET')
    if client_id and client_secret:
        _google_enabled = True
        oauth.register(
            name='google',
            client_id=client_id,
            client_secret=client_secret,
            server_metadata_url='https://accounts.google.com/.well-known/openid-configuration',
            client_kwargs={'scope': 'openid email profile'},
        )
        print(f'[AUTH] Google OAuth configuré.')
    else:
        print('[AUTH] Google OAuth non configuré (GOOGLE_CLIENT_ID/SECRET manquants).')

    supabase_url = os.environ.get('SUPABASE_URL')
    supabase_key = os.environ.get('SUPABASE_KEY')
    if supabase_url and supabase_key:
        try:
            from supabase import create_client, ClientOptions
            # Timeout explicite : constaté en conditions réelles qu'une
            # connexion keep-alive du pool httpx peut finir en CLOSE_WAIT
            # (l'autre bout a fermé, le socket local ne le voit jamais) —
            # sans timeout explicite, l'appel .execute() bloque le thread
            # indéfiniment, sans lever d'exception, donc sans jamais être
            # rattrapé par les except Exception de db.py. Un job Cross Analyse
            # peut alors rester bloqué à "running" pour toujours malgré un
            # travail déjà terminé. Ce timeout transforme le blocage muet en
            # exception rapide et journalisée, rattrapable normalement.
            # `ClientOptions` doit venir de `supabase` (alias public de
            # SyncClientOptions) et non de `supabase.lib.client_options` — ce
            # dernier n'a pas le champ `storage` qu'attend create_client().
            _supabase = create_client(
                supabase_url, supabase_key,
                options=ClientOptions(postgrest_client_timeout=30),
            )
            print('[AUTH] Supabase connecté.')
        except Exception as e:
            print(f'[AUTH] Supabase indisponible, fallback users.json : {e}')


# ── Helpers session ───────────────────────────────────────────────────────────

def _open_session(user):
    session.permanent = True
    session['user_id']      = user['user_id']
    session['user_email']   = user.get('email', '')
    session['user_name']    = user.get('name', '') or user.get('email', '')
    session['user_picture'] = user.get('picture', '')


# Identité de secours en dev local (AUTH_ENABLED=false) : sans elle, toute
# route qui exige un user_id réel (ex. `_db.create_folder`) échoue en silence
# dès qu'aucune session n'existe — alors que le commentaire en tête de fichier
# promet que ce mode fait « passer toutes les routes ». N'a aucun effet quand
# AUTH_ENABLED=true : une vraie session reste alors obligatoire.
#
# user_id doit être un UUID valide — la colonne Supabase est typée uuid.
# 'dev-local' (chaîne littérale) n'en est pas un : chaque requête filtrée
# dessus (crédits, stratégies, mémoire de cas...) échouait avec
# invalid input syntax for type uuid: "dev-local", avalé en silence par les
# except Exception des fonctions d'écriture — trouvé en testant réellement
# une génération de stratégie en local (le solde de crédits ne bougeait
# jamais). Ce placeholder reste un UUID reconnaissable au premier coup d'œil
# dans les journaux ou la base plutôt qu'un UUID aléatoire quelconque.
_DEV_USER = {
    'user_id': 'dec0de00-0000-4000-8000-000000000001',
    'email':   'dev@local.gabriel',
    'name':    'Dev local',
    'picture': '',
}

# Le UUID valide (ci-dessus) suffit à ce que les requêtes Supabase filtrées
# dessus s'exécutent sans erreur — mais une requête sur une ligne qui n'a
# jamais été créée n'échoue pas non plus : elle réussit silencieusement en
# ne touchant aucune ligne. Le crédit affiché retombait donc toujours sur
# le défaut (voir get_user_credits), la déduction n'ayant jamais rien à
# mettre à jour — trouvé en vérifiant le solde après une génération réussie
# en local. Un vrai compte obtient sa ligne à l'inscription
# (_sb_upsert_google / register_email_user, plus bas dans ce fichier) ; le
# mode sans authentification contourne entièrement ce chemin. Provisionnée
# une seule fois par démarrage de processus. Supabase conserve son DEFAULT 300
# de colonne (voir _sb_upsert_google) ; le fallback JSON inscrit explicitement
# la même valeur puisqu'il ne dispose pas d'un schéma avec valeur par défaut.
_dev_user_provisioned = False


def _is_local_development():
    """Return whether the shared fictitious identity is safe to provision."""
    auth_disabled = os.environ.get('AUTH_ENABLED', 'false').lower() != 'true'
    deployed = (
        bool(os.environ.get('RENDER'))
        or bool(os.environ.get('RENDER_EXTERNAL_URL'))
        or os.environ.get('GABRIEL_ENV', '').lower() == 'production'
    )
    return auth_disabled and not deployed


def _ensure_dev_user_row():
    global _dev_user_provisioned
    if _dev_user_provisioned or not _is_local_development():
        return
    try:
        now = datetime.datetime.utcnow().isoformat()
        if _supabase:
            existing = _supabase.table(_TABLE).select('user_id').eq('user_id', _DEV_USER['user_id']).limit(1).execute()
            if not existing.data:
                _supabase.table(_TABLE).insert({
                    'user_id':    _DEV_USER['user_id'],
                    'email':      _DEV_USER['email'],
                    'name':       _DEV_USER['name'],
                    'created_at': now,
                    'last_login': now,
                }).execute()
        else:
            users = _load_json_users()
            existing = next(
                (row for row in users.values()
                 if isinstance(row, dict)
                 and str(row.get('user_id')) == _DEV_USER['user_id']),
                None,
            )
            if existing is None:
                from api.db import DEFAULT_FREE_CREDITS
                users[_DEV_USER['user_id']] = {
                    'user_id':    _DEV_USER['user_id'],
                    'email':      _DEV_USER['email'],
                    'name':       _DEV_USER['name'],
                    'created_at': now,
                    'last_login': now,
                    'credits':    DEFAULT_FREE_CREDITS,
                }
                _save_json_users(users)
    except Exception as e:
        print(f'[AUTH] _ensure_dev_user_row error : {e}')
        return
    _dev_user_provisioned = True


def current_user():
    if not session.get('user_id'):
        if os.environ.get('AUTH_ENABLED', 'false').lower() != 'true':
            _ensure_dev_user_row()
            return _DEV_USER
        return None
    return {
        'user_id': session['user_id'],
        'email':   session.get('user_email', ''),
        'name':    session.get('user_name', ''),
        'picture': session.get('user_picture', ''),
    }


_JSON_GET_PREFIXES = (
    '/status/', '/history', '/strategies', '/usage',
    '/memory/', '/profil/data', '/conversation/', '/feedback',
    '/business-context', '/contexte_business', '/rag/', '/creator/',
    '/satisfaction', '/performance', '/stripe/',
)

_AUTH_401_PAYLOAD = {
    'success':    False,
    'error':      'Votre session a expiré. Veuillez vous reconnecter.',
    'error_code': 'auth_required',
    'redirect':   '/login',
}


def _is_api_request():
    """True si la requête attend du JSON (pas une page HTML)."""
    if request.is_json:
        return True
    if request.method in ('POST', 'DELETE', 'PUT', 'PATCH'):
        return True
    return any(request.path.startswith(p) for p in _JSON_GET_PREFIXES)


def login_required(f):
    """Décorateur universel — JSON 401 pour API, redirect pour pages HTML."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if os.environ.get('AUTH_ENABLED', 'false').lower() != 'true':
            return f(*args, **kwargs)
        if not session.get('user_id'):
            if _is_api_request():
                return jsonify(_AUTH_401_PAYLOAD), 401
            return redirect('/login')
        return f(*args, **kwargs)
    return decorated


def login_required_api(f):
    """Décorateur explicite pour routes API — retourne toujours JSON 401."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if os.environ.get('AUTH_ENABLED', 'false').lower() != 'true':
            return f(*args, **kwargs)
        if not session.get('user_id'):
            return jsonify(_AUTH_401_PAYLOAD), 401
        return f(*args, **kwargs)
    return decorated


def login_required_page(f):
    """Décorateur explicite pour pages HTML — redirige vers /login."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if os.environ.get('AUTH_ENABLED', 'false').lower() != 'true':
            return f(*args, **kwargs)
        if not session.get('user_id'):
            return redirect('/login')
        return f(*args, **kwargs)
    return decorated


# ── Supabase — Google OAuth ───────────────────────────────────────────────────

def get_or_create_user(google_user_info):
    if _supabase:
        return _sb_upsert_google(google_user_info)
    return _json_upsert_google(google_user_info)


def _sb_upsert_google(info):
    now = datetime.datetime.utcnow().isoformat()
    res = _supabase.table(_TABLE).select('user_id,created_at').eq('google_id', info['sub']).execute()
    if res.data:
        _supabase.table(_TABLE).update({
            'last_login': now,
            'name':       info.get('name', ''),
            'picture':    info.get('picture', ''),
        }).eq('google_id', info['sub']).execute()
        return {**res.data[0], 'email': info.get('email',''), 'name': info.get('name',''), 'picture': info.get('picture','')}
    row = {
        'user_id':   str(uuid.uuid4()),
        'google_id': info['sub'],
        'email':     info.get('email', ''),
        'name':      info.get('name', ''),
        'picture':   info.get('picture', ''),
        'created_at': now,
        'last_login': now,
    }
    # 'credits' est fourni par le DEFAULT 300 de la colonne côté Supabase (voir
    # supabase/credits_migration.sql) — jamais envoyé explicitement ici : tant
    # que la migration n'a pas tourné sur l'instance Supabase, une clé
    # inconnue dans l'insert fait échouer TOUTE création de compte (PGRST204).
    _supabase.table(_TABLE).insert(row).execute()
    return row


# ── Supabase — Email / Password ───────────────────────────────────────────────

def register_email_user(email, password, name=''):
    """Crée un compte email. Retourne (user_dict, None) ou (None, error_str)."""
    email = email.strip().lower()
    if not email or not password:
        return None, 'Email et mot de passe requis.'
    if len(password) < 8:
        return None, 'Le mot de passe doit faire au moins 8 caractères.'

    if _supabase:
        existing = _supabase.table(_TABLE).select('user_id').eq('email', email).execute()
        if existing.data:
            return None, 'Un compte existe déjà avec cet email.'
        now = datetime.datetime.utcnow().isoformat()
        row = {
            'user_id':       str(uuid.uuid4()),
            'email':         email,
            'name':          name or email.split('@')[0],
            'password_hash': generate_password_hash(password, method=_PASSWORD_HASH_METHOD),
            'created_at':    now,
            'last_login':    now,
        }
        # Pas de 'credits' explicite ici — voir commentaire dans _sb_upsert_google.
        _supabase.table(_TABLE).insert(row).execute()
        return row, None
    else:
        users = _load_json_users()
        by_email = {v['email']: v for v in users.values()}
        if email in by_email:
            return None, 'Un compte existe déjà avec cet email.'
        now = datetime.datetime.now().isoformat()
        uid = str(uuid.uuid4())
        users[uid] = {
            'user_id':       uid,
            'email':         email,
            'name':          name or email.split('@')[0],
            'password_hash': generate_password_hash(password, method=_PASSWORD_HASH_METHOD),
            'created_at':    now,
            'last_login':    now,
            'credits':       300,
        }
        _save_json_users(users)
        return users[uid], None


def verify_email_user(email, password):
    """Vérifie email+mot de passe. Retourne (user_dict, None) ou (None, error_str)."""
    email = email.strip().lower()
    if _supabase:
        res = _supabase.table(_TABLE).select('*').eq('email', email).execute()
        if not res.data:
            return None, 'Email ou mot de passe incorrect.'
        user = res.data[0]
        if not user.get('password_hash'):
            return None, 'Ce compte utilise la connexion Google.'
        if not check_password_hash(user['password_hash'], password):
            return None, 'Email ou mot de passe incorrect.'
        _supabase.table(_TABLE).update({'last_login': datetime.datetime.utcnow().isoformat()}) \
                               .eq('user_id', user['user_id']).execute()
        return user, None
    else:
        users = _load_json_users()
        by_email = {v['email']: v for v in users.values()}
        user = by_email.get(email)
        if not user or not user.get('password_hash'):
            return None, 'Email ou mot de passe incorrect.'
        if not check_password_hash(user['password_hash'], password):
            return None, 'Email ou mot de passe incorrect.'
        return user, None


# ── Fallback JSON ─────────────────────────────────────────────────────────────

def _json_upsert_google(info):
    users = _load_json_users()
    now   = datetime.datetime.now().isoformat()
    gid   = info['sub']
    if gid not in users:
        users[gid] = {
            'user_id':   str(uuid.uuid4()),
            'google_id': gid,
            'email':     info.get('email', ''),
            'name':      info.get('name', ''),
            'picture':   info.get('picture', ''),
            'created_at': now,
            'credits':   300,
        }
    users[gid]['last_login'] = now
    _save_json_users(users)
    return users[gid]


def _load_json_users():
    if os.path.exists(_USERS_FILE):
        try:
            with open(_USERS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def _save_json_users(users):
    with open(_USERS_FILE, 'w', encoding='utf-8') as f:
        json.dump(users, f, ensure_ascii=False, indent=2)


# ── Routes ────────────────────────────────────────────────────────────────────

@auth_bp.route('/login')
def login_page():
    plan = request.args.get('plan', '') if request.args.get('plan') in _REDIRECT_PLANS else ''
    if session.get('user_id'):
        return _post_login_redirect(plan)
    error          = request.args.get('error')
    mode           = request.args.get('mode', 'login')
    error_msg = {
        'not_configured': 'Connexion Google non configurée.',
        'auth_failed':    'Connexion Google échouée. Réessayez.',
    }.get(error, error)
    return render_template('login.html', error=error_msg, mode=mode, plan=plan, google_enabled=_google_enabled)


@auth_bp.route('/login/email', methods=['POST'])
@rate_limit(_RL_LOGIN)
def login_email():
    email    = request.form.get('email', '')
    password = request.form.get('password', '')
    plan     = request.form.get('plan', '')
    user, err = verify_email_user(email, password)
    if err:
        return render_template('login.html', error=err, mode='email', prefill_email=email, plan=plan,
                               google_enabled=_google_enabled)
    _open_session(user)
    return _post_login_redirect(plan)


@auth_bp.route('/register', methods=['GET', 'POST'])
@rate_limit(_RL_LOGIN)
def register():
    if request.method == 'GET':
        plan = request.args.get('plan', '') if request.args.get('plan') in _REDIRECT_PLANS else ''
        return render_template('login.html', mode='register', plan=plan, google_enabled=_google_enabled)
    name     = request.form.get('name', '')
    email    = request.form.get('email', '')
    password = request.form.get('password', '')
    confirm  = request.form.get('confirm', '')
    plan     = request.form.get('plan', '')
    if password != confirm:
        return render_template('login.html', error='Les mots de passe ne correspondent pas.', mode='register',
                               prefill_email=email, prefill_name=name, plan=plan, google_enabled=_google_enabled)
    user, err = register_email_user(email, password, name)
    if err:
        return render_template('login.html', error=err, mode='register',
                               prefill_email=email, prefill_name=name, plan=plan, google_enabled=_google_enabled)
    _open_session(user)
    return _post_login_redirect(plan)


@auth_bp.route('/auth/google')
def auth_google():
    if not os.environ.get('GOOGLE_CLIENT_ID'):
        return redirect('/login?error=not_configured')
    # Le round-trip OAuth ne peut pas transporter notre propre query string —
    # on garde l'intention "plan choisi avant connexion" en session, lue par
    # auth_google_callback() une fois l'utilisateur revenu.
    plan = request.args.get('plan', '')
    if plan in _REDIRECT_PLANS:
        session['pending_plan'] = plan
    redirect_uri = url_for('auth.auth_google_callback', _external=True)
    safe_log_event('oauth_start', metadata={'generated_redirect_uri': redirect_uri})
    return oauth.google.authorize_redirect(redirect_uri)


@auth_bp.route('/auth/google/callback')
def auth_google_callback():
    safe_log_event('oauth_callback_received', metadata={'has_state': bool(request.args.get('state'))})
    plan = session.pop('pending_plan', '')
    try:
        token = oauth.google.authorize_access_token()
    except MismatchingStateError as e:
        safe_log_event('state_valid', metadata={'valid': False}, error=e)
        return redirect('/login?error=auth_failed')
    except OAuthError as e:
        safe_log_event('token_exchange_failure', metadata={'error_type': type(e).__name__}, error=e)
        return redirect('/login?error=auth_failed')
    except Exception as e:
        safe_log_event('token_exchange_failure', metadata={'error_type': type(e).__name__}, error=e)
        return redirect('/login?error=auth_failed')

    safe_log_event('state_valid', metadata={'valid': True})
    try:
        user_info = token.get('userinfo')
        if not user_info:
            safe_log_event('token_exchange_failure', metadata={'error_type': 'no_userinfo'})
            return redirect('/login?error=auth_failed')
        user = get_or_create_user(user_info)
        safe_log_event('token_exchange_success', user_id=user.get('user_id') if isinstance(user, dict) else None)
        _open_session(user)
        return _post_login_redirect(plan)
    except Exception as e:
        safe_log_event('token_exchange_failure', metadata={'error_type': type(e).__name__}, error=e)
        return redirect('/login?error=auth_failed')


@auth_bp.route('/logout')
def logout():
    session.clear()
    return redirect('/')


@auth_bp.route('/me')
def me():
    user = current_user()
    if not user:
        return jsonify({'authenticated': False}), 401
    return jsonify({'authenticated': True, **user})
