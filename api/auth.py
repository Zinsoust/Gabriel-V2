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
from werkzeug.security import generate_password_hash, check_password_hash

auth_bp = Blueprint('auth', __name__)
oauth   = OAuth()

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
            from supabase import create_client
            _supabase = create_client(supabase_url, supabase_key)
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


def current_user():
    if not session.get('user_id'):
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
    _supabase.table(_TABLE).insert(row).execute()
    return row


# ── Supabase — Email / Password ───────────────────────────────────────────────

def register_email_user(email, password, name=''):
    """Crée un compte email. Retourne (user_dict, None) ou (None, error_str)."""
    email = email.strip().lower()
    if not email or not password:
        return None, 'Email et mot de passe requis.'
    if len(password) < 6:
        return None, 'Le mot de passe doit faire au moins 6 caractères.'

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
    if session.get('user_id'):
        return redirect('/dossiers')
    error          = request.args.get('error')
    mode           = request.args.get('mode', 'login')
    error_msg = {
        'not_configured': 'Connexion Google non configurée.',
        'auth_failed':    'Connexion Google échouée. Réessayez.',
    }.get(error, error)
    return render_template('login.html', error=error_msg, mode=mode, google_enabled=_google_enabled)


@auth_bp.route('/login/email', methods=['POST'])
def login_email():
    email    = request.form.get('email', '')
    password = request.form.get('password', '')
    user, err = verify_email_user(email, password)
    if err:
        return render_template('login.html', error=err, mode='email', prefill_email=email,
                               google_enabled=_google_enabled)
    _open_session(user)
    return redirect('/dossiers')


@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'GET':
        return render_template('login.html', mode='register', google_enabled=_google_enabled)
    name     = request.form.get('name', '')
    email    = request.form.get('email', '')
    password = request.form.get('password', '')
    confirm  = request.form.get('confirm', '')
    if password != confirm:
        return render_template('login.html', error='Les mots de passe ne correspondent pas.', mode='register',
                               prefill_email=email, prefill_name=name, google_enabled=_google_enabled)
    user, err = register_email_user(email, password, name)
    if err:
        return render_template('login.html', error=err, mode='register',
                               prefill_email=email, prefill_name=name, google_enabled=_google_enabled)
    _open_session(user)
    return redirect('/dossiers')


@auth_bp.route('/auth/google')
def auth_google():
    if not os.environ.get('GOOGLE_CLIENT_ID'):
        return redirect('/login?error=not_configured')
    redirect_uri = url_for('auth.auth_google_callback', _external=True)
    return oauth.google.authorize_redirect(redirect_uri)


@auth_bp.route('/auth/google/callback')
def auth_google_callback():
    try:
        token     = oauth.google.authorize_access_token()
        user_info = token.get('userinfo')
        if not user_info:
            return redirect('/login?error=auth_failed')
        user = get_or_create_user(user_info)
        _open_session(user)
        return redirect('/dossiers')
    except Exception as e:
        print(f'[AUTH] Erreur OAuth callback : {e}')
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
