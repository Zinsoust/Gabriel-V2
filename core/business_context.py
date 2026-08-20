"""Accès aux mémoires Utilisateur, Business et Audience.

Extrait de ``app.py``, sans changement de comportement — c'est le même geste
déjà fait pour les outils du Psychologue (``core/analyzer.py``) et les
savoir-faire du Créateur (``agents/createur.py``) : les fonctions étaient
correctes, seulement enfermées dans un fichier que rien d'autre ne peut
importer. ``app.py`` reste la feuille de l'arbre d'imports ; ce module en est
maintenant une branche normale, lisible par le Memory Manager (voir
``core/memories.py``).

Trois mémoires, trois mécanismes de stockage distincts, gardés tels quels :

* **Utilisateur** — fichier JSON par compte (mécanisme le plus ancien,
  antérieur à l'Entretien stratégique).
* **Business** — cascade à trois niveaux : requête, puis Entretien
  stratégique (Supabase), puis profil utilisateur en dernier recours.
* **Audience** — rapports des trois agents pour un workspace, chargés
  seulement quand la conversation les appelle.
"""

import json
import os

from api import db as _db

_BASE_DIR     = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DATA_DIR     = os.path.join(_BASE_DIR, 'data')
_BRAIN_FILE   = os.path.join(_DATA_DIR, 'brain_profile.json')
_PROFILES_DIR = os.path.join(_DATA_DIR, 'profiles')
os.makedirs(_PROFILES_DIR, exist_ok=True)


# ─── Mémoire Utilisateur ──────────────────────────────────────────────────────

def get_user_profile(uid):
    """Charge le brain_profile de l'utilisateur courant (per-user)."""
    if uid:
        path = os.path.join(_PROFILES_DIR, f"{uid}.json")
        if os.path.exists(path):
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                pass
    # Fallback legacy (dev / migration)
    if os.path.exists(_BRAIN_FILE):
        try:
            with open(_BRAIN_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_user_profile(uid, data):
    """Sauvegarde le brain_profile par utilisateur."""
    if uid:
        path = os.path.join(_PROFILES_DIR, f"{uid}.json")
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    # Garder le fichier legacy à jour (pour dev / fallback)
    with open(_BRAIN_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ─── Mémoire Business ─────────────────────────────────────────────────────────

# L'Entretien stratégique (Context Builder) nomme ses champs autrement que le
# brain_profile historique. Les renvoyer bruts reviendrait à livrer un
# contexte que personne ne sait lire : les agents cherchent 'activite'/
# 'offre'/'cible' et trouveraient None, se croyant sans contexte alors que
# l'entretien l'a bien collecté.
_CB_TO_BRAIN = {
    'user_role':       'role_utilisateur',
    'activity':        'activite',
    'priority_offer':  'offre',
    'target_audience': 'cible',
    'business_model':  'modele_economique',
    'current_results': 'resultats_actuels',
    'main_objectives': 'objectif_principal',
    'strategic_vision':'vision_strategique',
    'constraints':     'contraintes',
    'resources':       'ressources',
    'business_name':   'nom_business',
}


def normalize_profile(p):
    """Normalise un profil CB ou brain_profile vers les clés brain_profile."""
    if not p:
        return {}
    result = {}
    for k, v in p.items():
        result[_CB_TO_BRAIN.get(k, k)] = v
    return result


def resolve_business_context(data, uid):
    """Résout le contexte business depuis le body, sinon l'Entretien stratégique
    V1.1 (source de vérité réelle depuis ce chantier — gabriel_context_fields),
    sinon l'ancien profil fichier par utilisateur en dernier recours.

    Trouvé en conditions réelles : templates/createur.html n'a jamais envoyé
    business_context dans son payload, donc /creator/generate retombait
    systématiquement sur get_user_profile(uid) — un mécanisme fichier
    distinct et antérieur à l'Entretien stratégique, vide pour tout compte
    qui n'a jamais utilisé l'ancien flux. Résultat : le Créateur écrivait
    sans jamais connaître l'activité, l'offre ou la cible réelles renseignées
    pendant l'entretien vocal — silencieusement, sans erreur."""
    business_context = data.get('business_context') or {}
    if business_context:
        return normalize_profile(business_context)
    if uid:
        v1_fields = _db.get_context_fields(uid)
        if v1_fields:
            return normalize_profile(v1_fields)
    return get_user_profile(uid) or {}


# ─── Mémoire Audience ──────────────────────────────────────────────────────────

def load_workspace_context(folder_id, user_id, include_agents=()):
    """Charge les productions vérifiées, seulement lorsqu'elles sont requises.

    Les identifiants présents dans le workspace suffisent à savoir qu'un agent
    a produit un résultat. Le contenu complet n'est relu que si le plan de
    conversation l'autorise : cela maintient la réponse rapide et évite de
    traiter un rapport comme un contexte implicite à chaque message.
    """
    state = {
        'folder': None,
        'psycho_data': {},
        'strategy_data': {},
        'createur_data': {},
        'availability': {'psychologue': False, 'stratege': False, 'createur': False},
        'loaded_agents': [],
    }
    if not folder_id or not user_id:
        return state

    folder = _db.get_folder_by_id(folder_id, user_id)
    if not folder:
        return state
    state['folder'] = folder
    requested = {
        str(agent) for agent in include_agents
        if str(agent) in {'psychologue', 'stratege', 'createur'}
    }

    analysis_id = folder.get('analysis_id') or ''
    state['availability']['psychologue'] = bool(analysis_id)
    if analysis_id and 'psychologue' in requested:
        entry = _db.get_analysis_by_id(analysis_id, user_id)
        # Un résultat est lisible uniquement depuis le workspace qui le
        # référence. Les anciennes données locales sans folder_id restent
        # compatibles, mais un folder_id explicite doit correspondre.
        if entry and entry.get('folder_id') and entry.get('folder_id') != folder_id:
            entry = None
        state['psycho_data'] = (entry or {}).get('full_result') or {}
        if not isinstance(state['psycho_data'], dict):
            state['psycho_data'] = {}
        if state['psycho_data']:
            state['loaded_agents'].append('psychologue')

    strategy_id = folder.get('strategy_id') or ''
    state['availability']['stratege'] = bool(strategy_id)
    if strategy_id and 'stratege' in requested:
        entry = _db.get_strategy_by_id(strategy_id, user_id)
        if entry and entry.get('folder_id') and entry.get('folder_id') != folder_id:
            entry = None
        state['strategy_data'] = (entry or {}).get('strategy_result') or {}
        if not isinstance(state['strategy_data'], dict):
            state['strategy_data'] = {}
        if state['strategy_data']:
            state['loaded_agents'].append('stratege')

    creator_output_id = folder.get('creator_output_id') or ''
    state['availability']['createur'] = bool(creator_output_id)
    if creator_output_id and 'createur' in requested:
        entry = _db.get_job(creator_output_id, user_id=user_id)
        if entry and entry.get('folder_id') and entry.get('folder_id') != folder_id:
            entry = None
        result = (entry or {}).get('result_data') or {}
        if not isinstance(result, dict):
            result = {}
        # Les jobs Créateur historiques peuvent stocker directement le contenu
        # ou l'envelopper dans un résultat de job.
        state['createur_data'] = result.get('data') if isinstance(result.get('data'), dict) else result
        if state['createur_data']:
            state['loaded_agents'].append('createur')
    return state
