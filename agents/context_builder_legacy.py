import os

from core import llm_client as _llm
import json
from core.security import wrap_untrusted_content

# Champs à collecter, avec label humain et question associée
CONTEXT_FIELDS = [
    {
        "key": "user_role",
        "label": "Rôle",
        "question": "Quel est votre rôle dans ce projet ? (fondateur, consultant, coach, créateur…)",
        "required": True,
    },
    {
        "key": "activity",
        "label": "Activité",
        "question": "Quelle est votre activité principale ?",
        "required": True,
    },
    {
        "key": "priority_offer",
        "label": "Offre prioritaire",
        "question": "Quelle offre voulez-vous développer ou vendre en priorité ?",
        "required": True,
    },
    {
        "key": "target_audience",
        "label": "Cible",
        "question": "À qui s'adresse principalement votre offre ?",
        "required": True,
    },
    {
        "key": "business_model",
        "label": "Modèle économique",
        "question": "Comment gagnez-vous de l'argent aujourd'hui — ou comment comptez-vous le faire ?",
        "required": True,
    },
    {
        "key": "current_results",
        "label": "Résultats actuels",
        "question": "Quels sont vos résultats actuels ? (chiffres, audience, clients…)",
        "required": True,
    },
    {
        "key": "main_objectives",
        "label": "Objectif principal",
        "question": "Quel est votre objectif prioritaire maintenant ?",
        "required": True,
    },
    {
        "key": "strategic_vision",
        "label": "Vision stratégique",
        "question": "Quelle est votre vision ou intuition actuelle pour ce projet ?",
        "required": False,
    },
    {
        "key": "constraints",
        "label": "Contraintes",
        "question": "Avez-vous des contraintes importantes à prendre en compte ? (temps, budget, équipe…)",
        "required": False,
    },
    {
        "key": "resources",
        "label": "Ressources disponibles",
        "question": "Quelles ressources avez-vous à disposition ? (équipe, budget, outils, audience…)",
        "required": False,
    },
]

REQUIRED_KEYS = [f["key"] for f in CONTEXT_FIELDS if f["required"]]
ALL_KEYS      = [f["key"] for f in CONTEXT_FIELDS]
FIELD_BY_KEY  = {f["key"]: f for f in CONTEXT_FIELDS}

_EXTRACT_SYSTEM = """Tu es un assistant d'extraction de contexte business pour Gabriel.

Ta mission : analyser le message de l'utilisateur et extraire toutes les informations business présentes.

Champs à extraire (seulement si l'information est clairement présente dans le message) :
- user_role : rôle ou poste de la personne (fondateur, coach, consultant, créateur de contenu…)
- activity : activité principale ou secteur (formation en ligne, coaching, e-commerce, SaaS…)
- priority_offer : offre ou produit prioritaire (programme, service, formation, logiciel…)
- target_audience : cible ou audience visée (entrepreneurs débutants, femmes 30-45 ans, PME…)
- business_model : comment la personne gagne de l'argent (vente directe, abonnement, freelance, formation…)
- current_results : résultats actuels mesurables (CA, abonnés, clients, MRR…)
- main_objectives : objectif prioritaire actuel (doubler le CA, lancer un produit, 1000 abonnés…)
- strategic_vision : vision ou intuition pour le projet (devenir la référence, automatiser…)
- constraints : contraintes réelles (budget limité, seul, peu de temps…)
- resources : ressources disponibles (équipe, outils, audience existante, budget…)

Règles STRICTES :
1. Extraire UNIQUEMENT ce qui est explicitement dit — ne pas inférer ni inventer
2. Si un champ n'est pas mentionné, ne pas l'inclure dans le JSON
3. Les valeurs doivent être des phrases courtes et précises, pas des mots seuls
4. Si le message est vague ou incomplet sur un champ, ne pas l'inclure

Réponds UNIQUEMENT avec un JSON valide contenant les champs extraits. Exemple :
{"user_role": "fondateur de startup", "activity": "formation en ligne sur la finance personnelle"}"""

_CONVERSATION_SYSTEM = """Tu es Gabriel, un conseiller business senior — direct, humain, précis.

Tu mènes une conversation pour comprendre le projet business de l'utilisateur.
Tu viens de recevoir leur dernier message.

Ta réponse doit :
1. Accuser réception naturellement si le message apporte une information (1 phrase max, sans reformuler ce qu'ils ont dit mot pour mot)
2. Si l'utilisateur pose une vraie question, y répondre brièvement (1-2 phrases)
3. Enchaîner avec UNE SEULE question pour collecter la prochaine info manquante
4. Rester court : 2-3 phrases maximum au total

Règles :
- Ne pas répéter ce que l'utilisateur vient de dire
- Ne pas énumérer les informations déjà connues
- Si le message est vague ou hors-sujet, recentrer doucement vers la prochaine question
- Ton naturel, pas robotique — comme un vrai conseiller qui discute
- Répondre en français

Réponds UNIQUEMENT avec ta réponse conversationnelle, sans balises ni explications."""


def _call_llm(prompt, system, max_tokens=800):
    """Entretien historique (/context-chat) — passe par la couche commune."""
    return _llm.complete_text(
        prompt,
        tier="deep",
        max_tokens=max_tokens,
        temperature=0.1,
        timeout_ms=60_000,
        retry=_llm.RETRY_NONE,
        label="context_chat_legacy",
        system=system,
    )

# Le prompt d'extraction demande déjà de rejeter les réponses vagues (règle 4),
# mais rien ne vérifiait que ce soit vraiment appliqué — un LLM a tendance à
# accepter trop facilement ("quelques clients" devient un champ "rempli").
# Garde-fou déterministe : une valeur trop courte ou trop générique est
# rejetée au niveau code, pas seulement laissée à l'appréciation du modèle.
_VAGUE_PATTERNS = [
    "je sais pas", "je ne sais pas", "pas grand chose", "pas encore",
    "un peu de tout", "pas beaucoup", "rien de precis", "rien de précis",
    "pas vraiment", "pas trop", "aucune idee", "aucune idée", "on verra",
    "pas defini", "pas défini", "pas encore defini", "pas encore défini",
]


def _is_specific_enough(value: str) -> bool:
    """Rejette les réponses trop courtes ou trop génériques pour être
    exploitables par le Stratège — corrige le profil business "déclaratif,
    non vérifié" identifié dans l'audit."""
    v = value.strip().lower()
    if len(v.split()) < 2:
        return False
    return not any(p in v for p in _VAGUE_PATTERNS)


def extract_context(message: str, current_context: dict) -> dict:
    """Extrait les champs business depuis le message utilisateur.
    Retourne {"context": dict fusionné, "rejected_vague": [labels rejetés]} —
    un champ rejeté reste "manquant" pour qu'on redemande une réponse précise
    au lieu d'accepter une esquive comme si c'était une vraie information."""
    ctx_summary = ""
    if current_context:
        lines = [f"{FIELD_BY_KEY[k]['label']}: {v}" for k, v in current_context.items() if v and k in FIELD_BY_KEY]
        if lines:
            ctx_summary = "Contexte déjà collecté :\n" + "\n".join(lines) + "\n\n"

    prompt = f"{ctx_summary}Message de l'utilisateur (extraire l'information uniquement) :\n{wrap_untrusted_content(message)}"
    try:
        raw = _call_llm(prompt, _EXTRACT_SYSTEM, max_tokens=500)
        start = raw.find('{')
        end   = raw.rfind('}') + 1
        extracted = json.loads(raw[start:end]) if start >= 0 and end > start else {}
    except Exception:
        extracted = {}

    # Fusionner avec le contexte existant (ne pas écraser)
    merged = dict(current_context or {})
    rejected_vague = []
    for key, value in extracted.items():
        if key not in ALL_KEYS or not value or not isinstance(value, str) or not value.strip():
            continue
        v = value.strip()
        if _is_specific_enough(v):
            merged[key] = v
        else:
            rejected_vague.append(FIELD_BY_KEY[key]['label'])

    return {"context": merged, "rejected_vague": rejected_vague}


def get_missing_fields(context: dict) -> list:
    """Retourne tous les champs manquants (requis + optionnels)."""
    missing = []
    for f in CONTEXT_FIELDS:
        val = context.get(f["key"], "")
        if not (val and isinstance(val, str) and val.strip()):
            missing.append(f)
    return missing


def get_missing_required(context: dict) -> list:
    """Retourne les champs requis manquants."""
    return [f for f in get_missing_fields(context) if f["required"]]


def compute_completion(context: dict) -> float:
    """Score de complétude 0.0 → 1.0 basé sur les champs requis."""
    filled = sum(
        1 for k in REQUIRED_KEYS
        if (context.get(k) or "").strip()
    )
    return round(filled / len(REQUIRED_KEYS), 2)


def is_ready(context: dict) -> bool:
    """True si tous les champs requis sont renseignés."""
    return compute_completion(context) >= 1.0


def generate_response(message: str, updated_context: dict, rejected_vague: list = None) -> str:
    """
    Génère une réponse conversationnelle qui :
    - Reconnaît ce que l'utilisateur vient de dire
    - Demande naturellement la prochaine info manquante
    - Peut répondre à une question si nécessaire
    Si rejected_vague est non-vide, la réponse relance sur une réponse plus
    précise au lieu de répéter la question de base telle quelle.
    """
    missing_req = get_missing_required(updated_context)
    missing_opt = get_missing_fields(updated_context)

    # Contexte complet
    if not missing_req:
        if not missing_opt:
            return "Parfait — j'ai tout ce qu'il me faut. Cliquez sur « Générer la stratégie »."
        next_field = missing_opt[0]
    else:
        next_field = missing_req[0]

    ctx_lines = [
        f"{FIELD_BY_KEY[k]['label']}: {updated_context[k]}"
        for k in ALL_KEYS
        if (updated_context.get(k) or "").strip()
    ]
    ctx_block = ("Contexte déjà connu :\n" + "\n".join(ctx_lines)) if ctx_lines else "Aucun contexte collecté pour l'instant."

    vague_note = ""
    if rejected_vague:
        vague_note = (
            f"\n\nATTENTION : la réponse de l'utilisateur sur \"{', '.join(rejected_vague)}\" "
            "était trop vague pour être exploitée (ex: \"je sais pas\", \"un peu de tout\"). "
            "Relance-le gentiment en lui demandant un exemple concret ou un chiffre, "
            "sans répéter mot pour mot la question de base."
        )

    prompt = (
        f"{ctx_block}\n\n"
        f"Prochain champ à collecter : {next_field['label']}\n"
        f"Question de base : {next_field['question']}\n\n"
        f"Dernier message de l'utilisateur : \"{message}\"{vague_note}\n\n"
        "Génère ta réponse conversationnelle (2-3 phrases max)."
    )

    try:
        return _call_llm(prompt, _CONVERSATION_SYSTEM, max_tokens=150)
    except Exception:
        return next_field["question"]


_RESET_TRIGGERS = [
    "nouveau contexte", "nouvelle contexte", "nouveau context",
    "reset", "réinitialiser", "reinitialiser", "recommencer",
    "changer mon contexte", "modifier mon contexte", "changer le contexte",
    "tout effacer", "repartir de zéro", "repartir à zéro",
    "nouveau business", "nouvelle activité", "j'ai changé",
]

def _is_reset_intent(message: str) -> bool:
    """Détecte si le message exprime une intention de réinitialiser le contexte."""
    msg_lower = message.lower().strip()
    return any(trigger in msg_lower for trigger in _RESET_TRIGGERS)


def process_message(message: str, current_context: dict) -> dict:
    """
    Point d'entrée principal du Context Builder.
    Reçoit un message + contexte actuel, retourne l'état mis à jour.
    """
    if _is_reset_intent(message):
        first_q = CONTEXT_FIELDS[0]["question"]
        return {
            "updated_context":  {},
            "missing_fields":   REQUIRED_KEYS,
            "next_question":    f"Bien sûr, on repart de zéro. {first_q}",
            "completion_score": 0.0,
            "filled_count":     0,
            "total_required":   len(REQUIRED_KEYS),
            "is_ready":         False,
        }

    extraction     = extract_context(message, current_context)
    updated        = extraction["context"]
    rejected_vague = extraction["rejected_vague"]
    missing_req  = get_missing_required(updated)
    score        = compute_completion(updated)
    ready        = is_ready(updated)
    # generate_response() a déjà son propre court-circuit (aucun appel LLM) quand
    # required ET optional sont tous remplis — ne pas dupliquer cette condition ici
    # avec `ready` (required seul) : ça ignorait silencieusement tout message envoyé
    # une fois les champs requis complets alors que des champs optionnels restaient
    # à collecter (ex: l'utilisateur dit "j'en ai un autre" et se fait répondre le
    # même message générique en boucle).
    response     = generate_response(message, updated, rejected_vague)

    filled_count = sum(
        1 for k in REQUIRED_KEYS if (updated.get(k) or "").strip()
    )

    return {
        "updated_context":  updated,
        "missing_fields":   [f["key"] for f in missing_req],
        "next_question":    response,
        "completion_score": score,
        "filled_count":     filled_count,
        "total_required":   len(REQUIRED_KEYS),
        "is_ready":         ready,
        "rejected_vague":   rejected_vague,
    }
