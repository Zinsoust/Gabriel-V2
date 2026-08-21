# ═══════════════════════════════════════════════════════════════════════════
# INTENT ENGINE — routage d'intention de l'Orchestrateur
#
# Heuristique d'abord, pas d'appel LLM : classer une demande doit être
# instantané (le brief fondateur : « toutes les demandes ne doivent pas
# déclencher le même niveau d'intelligence »). On décide :
#   - le NIVEAU de réponse attendu (rapide vs approfondi),
#   - l'AGENT vers lequel orienter (psychologue / stratege / createur / None),
#   - la RAISON de cette orientation, formulée pour l'utilisateur.
#
# La réponse conversationnelle elle-même reste produite par le LLM dans la
# route ; ce module ne fait que la cadrer.
# ═══════════════════════════════════════════════════════════════════════════

import re
import unicodedata

# ── Les trois bureaux : métadonnées d'orientation ────────────────────────────
AGENTS = {
    "psychologue": {
        "label": "Le Psychologue — analyser cette audience",
        "purpose": "comprendre ce que votre audience ressent, ses frustrations, ses aspirations et les profils qui la composent",
        "href": "/psychologue",
        "cta": "Ouvrir le Psychologue",
    },
    "stratege": {
        "label": "Le Stratège — construire la décision",
        "purpose": "transformer ce que l'on sait de l'audience en une décision claire : positionnement, offre, message",
        "href": "/stratege",
        "cta": "Ouvrir le Stratège",
    },
    "createur": {
        "label": "Le Créateur — produire le contenu",
        "purpose": "exécuter la décision en contenus prêts à publier, dans le ton et le canal choisis",
        "href": "/createur",
        "cta": "Ouvrir le Créateur",
    },
}

def _norm(text):
    """Minuscule sans accents — pour une correspondance de mots-clés robuste."""
    text = (text or "").lower()
    text = unicodedata.normalize("NFD", text)
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    return text


# Mots-clés par bureau. Volontairement larges : mieux vaut orienter souvent et
# laisser l'utilisateur ignorer la carte que ne jamais guider.
_KEYWORDS = {
    "psychologue": [
        "audience", "cible", "client", "ressent", "emotion", "psycholog",
        "commentaire", "persona", "frustration", "aspiration", "besoin",
        "comprendre les gens", "comprendre mon public", "avatar", "douleur",
        "ce qu'ils veulent", "ce qu'ils pensent", "analyser mon public",
    ],
    "stratege": [
        "strategie", "decision", "positionnement", "offre", "prix", "pricing",
        "canal", "roadmap", "plan", "vision", "modele economique", "differenci",
        "convient", "pertinent", "faut-il", "dois-je", "quelle direction",
        "que faire", "comment me positionner", "business model",
    ],
    "createur": [
        "creer", "rediger", "ecrire", "post", "publication", "script", "video",
        "publicite", "pub ", "contenu", "texte", "legende", "caption", "email",
        "newsletter", "accroche", "hook", "carrousel", "reel", "tiktok",
        "linkedin post", "page de vente",
    ],
}

# Signaux d'une demande complexe → réponse approfondie (plus de tokens, ton
# analytique). Le reste passe en réponse rapide.
_DEEP_SIGNALS = [
    "pourquoi", "analyse", "compare", "coherent", "coherence", "risque",
    "faiblesse", "point faible", "est-ce que", "devrais-je", "faut-il",
    "explique", "detaille", "approfond", "strategie", "critique", "evalue",
    "je ne sais pas si", "je me demande", "j'hesite", "aide-moi a decider",
]

_GREETING = re.compile(r"^\s*(bonjour|salut|hello|coucou|bonsoir|hey|yo)\b", re.I)
_THANKS = re.compile(r"^\s*(merci|thanks|thank you)(?:\s+[!.?]*)?$", re.I)
_TRANSVERSAL_SIGNALS = [
    "resume", "synthese", "compare", "coherence", "coherent",
    "contradiction", "verifie", "critique", "avis sur", "qu'en penses-tu",
    "ce qui ne va pas", "point faible", "pourquoi cette strategie",
]


def _detect_agent(norm_msg):
    """Retourne (agent, score) du bureau le plus sollicité, ou (None, 0)."""
    scores = {}
    for agent, words in _KEYWORDS.items():
        scores[agent] = sum(1 for w in words if w in norm_msg)
    best = max(scores, key=scores.get)
    return (best, scores[best]) if scores[best] > 0 else (None, 0)


def _detect_level(norm_msg):
    """« quick » par défaut ; « deep » si la demande porte un vrai raisonnement."""
    if _GREETING.match(norm_msg) and len(norm_msg) < 40:
        return "quick"
    if any(sig in norm_msg for sig in _DEEP_SIGNALS):
        return "deep"
    # Message long = probablement une situation à démêler.
    if len(norm_msg) > 220:
        return "deep"
    return "quick"


def response_max_tokens(level):
    """Budget de sortie selon le niveau — rapide reste concis, approfondi respire."""
    return 1500 if level == "deep" else 600


def classify_intent(message, has_psycho=False, has_strategy=False, has_createur=False):
    """
    Classe une demande utilisateur. Ne fait AUCUN appel réseau.

    Retourne :
      {
        'level': 'quick' | 'deep',
        'agent': 'psychologue' | 'stratege' | 'createur' | None,
        'reason': str,          # pourquoi ce bureau, formulé pour l'utilisateur
        'confidence': float,    # 0..1 indicatif
      }
    """
    norm = _norm(message)
    level = _detect_level(norm)
    agent, score = _detect_agent(norm)

    # Dans une conversation Gabriel, un lien social transmis seul est une
    # source de travail implicite, pas une question vague. Cette règle évite de
    # perdre le fil quand l'utilisateur répond simplement en collant son lien.
    if not agent and any(host in norm for host in (
        "youtube.com", "youtu.be", "instagram.com", "tiktok.com",
    )):
        agent, score = "psychologue", 2

    is_bare_greeting = bool(_GREETING.match(norm)) and score == 0 and len(norm) < 40
    if is_bare_greeting:
        return {
            "kind": "greeting", "level": "quick", "agent": None,
            "reason": "", "confidence": 1.0,
        }

    if _THANKS.match(norm):
        return {
            "kind": "thanks", "level": "quick", "agent": None,
            "reason": "", "confidence": 1.0,
        }

    # Synthétiser, comparer ou challenger des productions existantes est le
    # cœur du rôle transversal : ne pas renvoyer l'utilisateur vers un bureau.
    if any(signal in norm for signal in _TRANSVERSAL_SIGNALS):
        return {
            "kind": "transversal", "level": level, "agent": None,
            "reason": "", "confidence": 0.9,
        }

    # Journey : si l'utilisateur veut créer/décider mais que l'amont manque,
    # on le renvoie vers l'étape réellement nécessaire d'abord (le brief :
    # « avant de créer la publicité, je recommande de vérifier la cible »).
    reason = ""
    if agent == "createur" and not has_strategy:
        if not has_psycho:
            agent = "psychologue"
            reason = ("Avant de produire du contenu, il faut savoir à qui l'on parle vraiment. "
                      "Commençons par comprendre cette audience.")
        else:
            agent = "stratege"
            reason = ("L'audience est analysée, mais il manque encore la décision qui guide le contenu. "
                      "Passons par le Stratège d'abord.")
    elif agent == "stratege" and not has_psycho:
        # On peut décider sans Psychologue, mais on le signale.
        reason = ("On peut avancer sur la décision, mais elle sera plus solide fondée sur une analyse "
                  "réelle de l'audience. Le Psychologue peut la fournir si besoin.")
    elif agent:
        reason = f"Pour cela, {AGENTS[agent]['purpose']}."

    confidence = min(1.0, 0.4 + 0.2 * score) if score else 0.3
    return {
        "kind": "specialist_request" if agent else "conversation",
        "level": level,
        "agent": agent,
        "reason": reason,
        "confidence": confidence,
    }


def build_recommendation(intent, has_psycho=False, has_strategy=False, has_createur=False):
    """
    Transforme une intention en carte d'orientation pour le front, ou None.

    On ne recommande pas un bureau dont le travail est déjà fait, SAUF si
    l'utilisateur le vise explicitement (score de mots-clés capté en amont via
    intent['reason'] non vide et agent inchangé).
    """
    agent = intent.get("agent")
    if not agent or agent not in AGENTS:
        return None

    done = {"psychologue": has_psycho, "stratege": has_strategy, "createur": has_createur}
    # Si ce bureau a déjà produit et qu'aucune raison explicite ne le redemande,
    # on ne réoriente pas vers lui.
    if done.get(agent) and not intent.get("reason"):
        return None

    meta = AGENTS[agent]
    return {
        "agent": agent,
        "label": meta["label"],
        "reason": intent.get("reason") or meta["purpose"].capitalize() + ".",
        "cta": meta["cta"],
        "href": meta["href"],
    }


def build_handoff(agent, message, business_context=None, has_psycho=False, has_strategy=False):
    """
    Paquet compact transmis au bureau ciblé — pas l'historique brut, seulement
    l'utile (brief fondateur). Sérialisable, court, sans donnée sensible.
    """
    bc = business_context or {}
    return {
        "user_goal": (message or "")[:400],
        "target_agent": agent,
        "source_agent": "orchestrateur",
        "known_context": {
            "activite": bc.get("activite") or bc.get("activity") or "",
            "offre": bc.get("offre") or bc.get("offer") or "",
            "cible": bc.get("cible") or bc.get("current_target") or bc.get("target") or "",
        },
        "upstream_done": {
            "psychologue": bool(has_psycho),
            "stratege": bool(has_strategy),
        },
    }
