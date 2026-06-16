import os
import json
import uuid
import datetime
from flask import Flask, render_template, request, jsonify
from dotenv import load_dotenv

_env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
load_dotenv(_env_path, override=True)

from orchestrator import Gabriel
from memory import GabrielMemory
from scraper import (
    scrape_youtube,
    scrape_instagram_rapidapi,
    scrape_tiktok_rapidapi,
    parse_manual_comments,
)

app = Flask(__name__)
app.config['TEMPLATES_AUTO_RELOAD'] = True
gabriel = Gabriel()
memory  = GabrielMemory()

_BASE_DIR      = os.path.dirname(os.path.abspath(__file__))
_BRAIN_FILE    = os.path.join(_BASE_DIR, 'brain_profile.json')
_HISTORY_FILE  = os.path.join(_BASE_DIR, 'history.json')
_CONTEXT_FILE  = os.path.join(_BASE_DIR, 'contexte_business.json')

# Cache en mémoire des analyses psychologiques (max 20 entrées)
# Clé : analysis_id  |  Valeur : {psycho, title, video_context}
_psycho_cache = {}

brain_profile = {}
if os.path.exists(_BRAIN_FILE):
    try:
        with open(_BRAIN_FILE, 'r', encoding='utf-8') as f:
            brain_profile = json.load(f)
    except Exception:
        pass


# ─── Historique ──────────────────────────────────────────────────────────────

def _load_history():
    if os.path.exists(_HISTORY_FILE):
        try:
            with open(_HISTORY_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    return []


def _save_history(entry):
    history = _load_history()
    history.insert(0, entry)
    history = history[:20]
    with open(_HISTORY_FILE, 'w', encoding='utf-8') as f:
        json.dump(history, f, ensure_ascii=False, indent=2)


def _update_history_strategie(analysis_id, strategie_result):
    """Attache le résultat stratégique à l'entrée d'historique correspondante."""
    history = _load_history()
    for entry in history:
        if entry.get('analysis_id') == analysis_id:
            entry['strategie_result'] = strategie_result
            break
    with open(_HISTORY_FILE, 'w', encoding='utf-8') as f:
        json.dump(history, f, ensure_ascii=False, indent=2)


def _rebuild_cache():
    """Reconstruit _psycho_cache depuis l'historique au démarrage."""
    history = _load_history()
    for entry in history:
        aid = entry.get('analysis_id')
        full = entry.get('full_result')
        if aid and full:
            _psycho_cache[aid] = {
                'psycho':        full,
                'title':         entry.get('video_title', ''),
                'video_context': entry.get('video_context', ''),
            }

_rebuild_cache()


# ─── Routes ──────────────────────────────────────────────────────────────────

@app.route('/')
def landing():
    return render_template('landing.html')


@app.route('/app')
def index():
    from flask import make_response
    resp = make_response(render_template('index.html'))
    resp.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate'
    resp.headers['Pragma'] = 'no-cache'
    return resp


@app.route('/analyze', methods=['POST'])
def analyze():
    """
    Pipeline 1 — Analyse Psychologique.
    Scrape les commentaires, lance Le Psychologue, retourne les insights audience.
    Retourne également un analysis_id pour appeler /strategize ensuite.
    """
    data = request.json or {}
    source  = data.get('source', 'text')
    content = data.get('content', '').strip()

    if not content:
        return jsonify({'error': 'Contenu vide — collez une URL ou des commentaires'}), 400

    comments      = []
    video_context = ""
    video_title   = ""
    source_label  = source.capitalize()

    try:
        video_info = {}
        if source == 'youtube':
            comments, video_info = scrape_youtube(content)
            source_label  = 'YouTube'
            video_title   = video_info.get('title', '')
            if video_title:
                video_context = f"{video_title} — {video_info.get('channel', '')}"
        elif source == 'instagram':
            comments, _ = scrape_instagram_rapidapi(content)
            if not comments:
                comments = parse_manual_comments(content)
            source_label = 'Instagram'
        elif source == 'tiktok':
            comments, video_info = scrape_tiktok_rapidapi(content)
            if not comments:
                comments = parse_manual_comments(data.get('comments_text', ''))
            source_label = 'TikTok'
            video_title  = video_info.get('title', '')
            if video_title:
                video_context = f"{video_title} — {video_info.get('channel', '')}"
        else:
            comments     = parse_manual_comments(content)
            source_label = 'Texte libre'

        if not comments:
            return jsonify({'error': "Aucun commentaire trouvé. Vérifiez l'URL ou collez les commentaires manuellement."}), 400

        result = gabriel.run_psycho(comments, video_context, title=video_title)

        # Mise en cache pour /strategize
        analysis_id = str(uuid.uuid4())[:12]
        _psycho_cache[analysis_id] = {
            'psycho':        result,
            'title':         video_title,
            'video_context': video_context,
        }
        if len(_psycho_cache) > 20:
            del _psycho_cache[next(iter(_psycho_cache))]

        result['analysis_id']   = analysis_id
        result['source_label']  = source_label
        result['video_context'] = video_context

        _save_history({
            'analysis_id':      analysis_id,
            'date':             datetime.datetime.now().strftime('%d/%m/%Y %H:%M'),
            'source':           source_label,
            'contenu':          content[:80],
            'video_context':    video_context,
            'video_title':      video_title,
            'nb_commentaires':  result.get('meta', {}).get('total_commentaires', 0),
            'kpis':             {k: v['score'] for k, v in result.get('kpis', {}).items()},
            'has_data':         True,
            'full_result':      result,
        })

        return jsonify({'success': True, 'data': result})

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': f"Erreur d'analyse : {str(e)}"}), 500


@app.route('/strategize', methods=['POST'])
def strategize():
    """
    Pipeline 2 — Analyse Stratégique.
    Nécessite un analysis_id valide (issu de /analyze) et un profil projet.
    Lance Le Stratège et retourne décision, recommandations, marketing, identité.
    """
    global brain_profile
    data = request.json or {}

    analysis_id    = data.get('analysis_id', '')
    brain_override = data.get('brain_profile')  # profil envoyé depuis le formulaire

    if analysis_id not in _psycho_cache:
        return jsonify({
            'success': False,
            'error': "Analyse introuvable — lancez d'abord une Analyse Psychologique."
        }), 400

    cached        = _psycho_cache[analysis_id]
    psycho_data   = cached['psycho']
    title         = cached['title']

    # Le profil du formulaire prime sur le profil sauvegardé
    effective_profile = brain_override or brain_profile
    brain_context     = _format_brain_context(effective_profile)

    # Contexte mémoire — cas similaires passés
    memory_context = memory.get_memory_context(psycho_data, effective_profile)
    memory_summary = memory.get_similar_summary(psycho_data, effective_profile)

    try:
        result = gabriel.run_stratege(
            psycho_data,
            brain_context,
            title=title,
            memory_context=memory_context,
        )
        _update_history_strategie(analysis_id, result)
        # Stocker ce cas dans la mémoire
        memory.add_case(analysis_id, psycho_data, result.get('strategie', {}), effective_profile)
        return jsonify({'success': True, 'data': result, 'memory': memory_summary})

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'success': False, 'error': f"Erreur stratégique : {str(e)}"}), 500


@app.route('/profil', methods=['GET', 'POST'])
def profil():
    global brain_profile
    if request.method == 'POST':
        brain_profile = request.json or {}
        with open(_BRAIN_FILE, 'w', encoding='utf-8') as f:
            json.dump(brain_profile, f, ensure_ascii=False, indent=2)
        return jsonify({'success': True})
    return jsonify(brain_profile)


@app.route('/history', methods=['GET'])
def history():
    return jsonify(_load_history())


@app.route('/feedback', methods=['POST'])
def feedback():
    """Enregistrer le feedback utilisateur sur une stratégie."""
    data        = request.json or {}
    analysis_id = data.get('analysis_id', '')
    fb          = {
        'pertinente':   data.get('pertinente', ''),
        'va_appliquer': data.get('va_appliquer', ''),
        'resultat':     data.get('resultat', ''),
    }
    if not analysis_id:
        return jsonify({'success': False, 'error': 'analysis_id manquant'}), 400
    ok = memory.record_feedback(analysis_id, fb)
    return jsonify({'success': ok})


@app.route('/history/<int:idx>/load', methods=['GET'])
def load_history_entry(idx):
    history = _load_history()
    if not (0 <= idx < len(history)):
        return jsonify({'success': False, 'error': 'Index invalide'}), 404
    entry = history[idx]
    full = entry.get('full_result')
    if not full:
        return jsonify({'success': False, 'error': 'Données complètes non disponibles — analyse trop ancienne'}), 404
    return jsonify({
        'success':          True,
        'full_result':      full,
        'strategie_result': entry.get('strategie_result'),
    })


@app.route('/history/<int:idx>', methods=['DELETE'])
def delete_history(idx):
    h = _load_history()
    if 0 <= idx < len(h):
        h.pop(idx)
        with open(_HISTORY_FILE, 'w', encoding='utf-8') as f:
            json.dump(h, f, ensure_ascii=False, indent=2)
    return jsonify({'success': True})


# ─── Contexte Business ───────────────────────────────────────────────────────

@app.route('/contexte_business', methods=['GET', 'POST'])
def contexte_business():
    if request.method == 'POST':
        ctx = request.json or {}
        with open(_CONTEXT_FILE, 'w', encoding='utf-8') as f:
            json.dump(ctx, f, ensure_ascii=False, indent=2)
        return jsonify({'success': True})
    if os.path.exists(_CONTEXT_FILE):
        try:
            with open(_CONTEXT_FILE, 'r', encoding='utf-8') as f:
                return jsonify(json.load(f))
        except Exception:
            pass
    return jsonify({})


@app.route('/contexte_business/supplement', methods=['POST'])
def contexte_business_supplement():
    """Extrait le contexte business depuis un texte libre ou un PDF."""
    import anthropic as _ant
    data     = request.json or {}
    doc_type = data.get('type', 'text')
    existing = data.get('existing', {})

    field_descriptions = {
        'user_role':        "rôle de l'utilisateur (CEO, fondateur, consultant, coach, etc.)",
        'activity':         'activité ou entreprise (secteur, ce qu\'ils font)',
        'priority_offer':   'offre principale ou prioritaire',
        'target_audience':  'cible idéale (client idéal, douleurs, besoins)',
        'business_model':   'modèle économique (coaching, formation, abonnement, e-commerce…)',
        'current_results':  'résultats actuels (ventes, audience, ce qui fonctionne/bloque)',
        'main_objectives':  'objectifs prioritaires',
        'strategic_vision': 'vision stratégique',
        'business_name':    'nom du business ou projet',
        'additional_context': 'autres informations utiles non couvertes ci-dessus',
    }
    to_extract = {k: v for k, v in field_descriptions.items() if k not in existing}
    if not to_extract:
        return jsonify({'extracted': {}})

    fields_prompt = '\n'.join(f'- "{k}": {v}' for k, v in to_extract.items())
    prompt = (
        "Analyse ce document et extrais les informations business pertinentes.\n"
        "Retourne UNIQUEMENT un JSON valide (sans markdown) avec les champs que tu peux déduire clairement :\n"
        f"{fields_prompt}\n\n"
        "Règles :\n"
        "- N'inclus un champ QUE si l'information est clairement présente dans le document\n"
        "- Valeurs concises, max 200 caractères par champ\n"
        "- JSON pur, sans markdown ni backticks\n"
        'Exemple : {"activity": "Coach business en ligne", "priority_offer": "Programme 3 mois individuel"}'
    )

    try:
        client = _ant.Anthropic(api_key=os.getenv('ANTHROPIC_API_KEY'))

        if doc_type == 'pdf':
            pdf_data = data.get('data', '')
            if not pdf_data:
                return jsonify({'error': 'Données PDF manquantes'}), 400
            response = client.messages.create(
                model='claude-sonnet-4-6',
                max_tokens=700,
                messages=[{
                    'role': 'user',
                    'content': [
                        {'type': 'document', 'source': {'type': 'base64', 'media_type': 'application/pdf', 'data': pdf_data}},
                        {'type': 'text', 'text': prompt}
                    ]
                }]
            )
        else:
            content = data.get('content', '').strip()
            if not content:
                return jsonify({'error': 'Contenu vide'}), 400
            response = client.messages.create(
                model='claude-haiku-4-5-20251001',
                max_tokens=700,
                messages=[{'role': 'user', 'content': f'Document :\n"""\n{content[:5000]}\n"""\n\n{prompt}'}]
            )

        text = response.content[0].text.strip()
        try:
            extracted = json.loads(text)
        except Exception:
            from json_repair import repair_json
            extracted = json.loads(repair_json(text))
        return jsonify({'extracted': extracted})

    except Exception as e:
        import traceback; traceback.print_exc()
        return jsonify({'error': str(e)}), 500


@app.route('/contexte_business/chat', methods=['POST'])
def contexte_business_chat():
    import anthropic as _ant
    data    = request.json or {}
    message = data.get('message', '').strip()
    field   = data.get('field', '')
    if not message:
        return jsonify({'error': 'Message vide'}), 400

    field_labels = {
        'user_role':        "rôle de l'utilisateur (CEO, fondateur, consultant, coach, créateur de contenu…)",
        'activity':         'activité ou entreprise (secteur, ce qu\'ils font)',
        'priority_offer':   'offre principale ou prioritaire',
        'target_audience':  'cible idéale (client idéal, douleurs, besoins, niveau de maturité)',
        'business_model':   'modèle économique (comment ils gagnent de l\'argent)',
        'current_results':  'résultats actuels (ventes, audience, clients, ce qui fonctionne, ce qui bloque)',
        'main_objectives':  'objectifs prioritaires',
        'strategic_vision': 'vision stratégique et ambitions',
        # Legacy
        'business_name':    'nom du business ou projet',
        'offer':            'offre ou produit principal',
        'main_goal':        'objectif principal actuel',
        'current_problem':  'problème ou blocage actuel',
        'resources':        'ressources disponibles (budget, équipe, outils)',
        'constraints':      'contraintes principales',
        'channels':         'canaux de communication ou distribution',
        'market_context':   'contexte ou positionnement marché',
    }
    label = field_labels.get(field, field)

    prompt = (
        f"Tu es l'agent de collecte de contexte business de Gabriel.\n"
        f"L'utilisateur répond à la question sur : {label}\n"
        f"Réponse de l'utilisateur : \"{message}\"\n\n"
        f"Extrais la valeur essentielle et génère une confirmation courte en français.\n"
        f"Réponds UNIQUEMENT en JSON valide (sans markdown) :\n"
        f'{{\"extracted_value\": \"information reformulée clairement (max 120 caractères)\", '
        f'\"confirmation\": \"1 phrase de confirmation naturelle et encourageante\"}}'
    )
    try:
        client   = _ant.Anthropic(api_key=os.getenv('ANTHROPIC_API_KEY'))
        response = client.messages.create(
            model='claude-haiku-4-5-20251001',
            max_tokens=220,
            messages=[{'role': 'user', 'content': prompt}]
        )
        text = response.content[0].text.strip()
        return jsonify(json.loads(text))
    except Exception:
        return jsonify({'extracted_value': message[:120], 'confirmation': 'Noté, merci !'})


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _format_brain_context(profile):
    if not profile:
        return ""
    # Champs nouveaux en premier, puis aliases legacy pour rétrocompatibilité
    fields = [
        ('role_utilisateur',   'Rôle'),
        ('nom_business',       'Business'),
        ('activite',           'Activité'),
        ('offre',              'Offre prioritaire'),
        ('cible',              'Cible idéale'),
        ('modele_economique',  'Modèle économique'),
        ('resultats_actuels',  'Résultats actuels'),
        ('objectif_principal', 'Objectifs prioritaires'),
        ('vision_strategique', 'Vision stratégique'),
        # Legacy
        ('contraintes',        'Contraintes'),
        ('ressources',         'Ressources disponibles'),
        ('contexte_marche',    'Contexte marché'),
    ]
    lines = []
    for key, label in fields:
        raw = profile.get(key, '')
        val = raw.strip() if isinstance(raw, str) else ''
        if val:
            lines.append(f"{label} : {val}")
    return "\n".join(lines)


if __name__ == '__main__':
    print("Gabriel - Intelligence Humaine Avancée")
    print("http://localhost:5050")
    app.run(debug=False, port=5050, host='0.0.0.0', threaded=True)
