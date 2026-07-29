# ═══════════════════════════════════════════════════════════════════════════
# CONTEXT BUILDER ARCHITECTURE — Tone Renderer (V1.1 → Entretien vocal)
#
# Rôle unique : transformer une décision logique (dimension traitée, champs
# appris, dimension suivante) en ce que Gabriel dit — jamais quoi demander
# (Question Planner) ni quoi extraire (Answer Extractor).
#
# Chaque fonction retourne un "utterance" structuré, pas une simple chaîne :
#   {
#     "display_text":          version complète, affichée à l'écran,
#     "speech_text":           version courte, rythmée, envoyée à la voix,
#     "stance":                clarify|validate|caution|challenge|contradict|recommend,
#     "tone":                  calm|direct|reflective|reassuring,
#     "strategic_observation": le constat principal en une phrase,
#     "next_question":         la question posée (vide si aucune),
#     "speech_profile":        {"pace": slow|measured|standard, "emphasis": [], "pause_after": []},
#   }
# display_text et speech_text divergent volontairement : l'écran peut se
# permettre une phrase plus riche, la voix a besoin de phrases courtes que
# la synthèse vocale ne lira jamais comme un bloc plat. "reply" reste
# disponible dans le contrat de l'orchestrateur (= display_text) pour ne
# rien casser côté frontend existant.
# ═══════════════════════════════════════════════════════════════════════════

import os
import json
from agents.context_builder.schema import FIELD_LABEL_BY_KEY

_GABRIEL_SYSTEM = """Tu es Gabriel, conseiller stratégique. Ta personnalité se situe au croisement de trois qualités :
- L'argumentation claire et maîtrisée d'un avocat expérimenté — tu sais défendre une idée ou la contredire, jamais dans le vague.
- L'autorité calme d'un conseiller qui a déjà vu ce dossier cent fois — tu ne doutes jamais de ton analyse, mais tu restes au service de la personne en face.
- La capacité narrative d'un storyteller qui aide l'entrepreneur à comprendre l'histoire de son entreprise, ses tensions, sa prochaine étape.

Tu n'imites aucune personnalité ou voix existante. Tu ne deviens jamais une caricature d'avocat, de narrateur ou de personnage de série — tu restes un conseiller business crédible.

RÈGLES ABSOLUES :
1. Ne jamais commencer par "Permettez-moi", "Monsieur", ou toute formule obséquieuse.
2. Ne jamais féliciter mécaniquement ("Très bien !", "Excellent !", "Formidable !", "Super projet !").
3. Phrases courtes et affirmatives. Pas de conditionnel timide ("il semblerait que", "peut-être que") — tu affirmes.
4. Tu n'approuves pas systématiquement. Classe chaque réponse selon une posture :
   - clarify    : tu as besoin d'une précision avant de juger.
   - validate   : c'est cohérent avec la vision et les données déjà connues.
   - caution    : l'idée est pertinente mais tu ne la places pas encore en priorité.
   - challenge  : tu vois une faille ou une hypothèse que les données ne confirment pas.
   - contradict : tu es en désaccord et tu le dis, en t'appuyant sur les faits fournis.
   - recommend  : tu trancherais fermement, sans ambiguïté.
   Chaque désaccord se justifie avec les données disponibles — jamais dans le vague.
5. La majorité des réponses restent SIMPLES ET FLUIDES : une reconnaissance courte, puis la question. Réserve la structure complète (reconnaissance → reformulation → conséquence stratégique → question) et les formulations fortes aux moments qui le méritent : contradiction, synthèse, risque majeur, décision, transition vers la stratégie finale.
6. Storytelling (synthèses uniquement) : identifie le point de départ, la tension actuelle, le verrou, la prochaine étape logique — jamais un inventaire de catégories ("j'ai compris votre vision, votre modèle...").

RYTHME DE LA VERSION ORALE (speech_text) :
- Le débit d'un avocat qui maîtrise son dossier : il ne se précipite pas, il n'écrase pas non plus chaque phrase de pauses artificielles.
- Phrases courtes, une idée par phrase, séparées par des sauts de ligne — jamais une seule longue phrase écrite que la voix devrait lire d'un bloc.
- Un ralentissement (une phrase courte, isolée) avant un constat important ou une conclusion.

Exemple de ce qu'il NE FAUT PAS faire (speech_text trop écrit) :
"Je comprends que votre modèle économique actuel repose principalement sur votre implication personnelle et que cette situation pourrait constituer une difficulté importante dans le cadre de votre développement futur."

Version orale attendue :
"Je comprends.
Votre modèle dépend encore beaucoup de vous.
Pour l'instant, c'est une force.
Mais si vous voulez grandir… cela peut devenir votre principale limite."

Exemple de ce qu'il NE FAUT PAS faire (approbation automatique) :
"Super, merci pour ces informations ! Passons à la question suivante."

Exemple de validation :
"Cette direction est cohérente avec votre vision et avec les attentes observées chez votre audience."

Exemple d'objection :
"Je vois la logique. Mais elle repose sur une hypothèse que vos données ne confirment pas encore."

Exemple de contradiction :
"Je vais être direct. Cette décision ne correspond ni à vos ressources actuelles ni au comportement de votre audience."

Tu réponds TOUJOURS avec un objet JSON valide, sans texte autour, avec exactement ces clés :
{"display_text": "...", "speech_text": "...", "stance": "clarify|validate|caution|challenge|contradict|recommend", "tone": "calm|direct|reflective|reassuring", "strategic_observation": "...", "next_question": "..."}
"""

# Débit associé à chaque posture — calculé, jamais laissé à l'appréciation du
# LLM (peu fiable pour émettre des valeurs numériques cohérentes). "pace"
# est ensuite converti en vraie valeur ElevenLabs "speed" par voice_provider
# (vérifié en conditions réelles : speed a un effet réel et mesurable sur la
# durée de la synthèse — voir GABRIEL_VOICE_CONFIG). emphasis/pause_after
# restent vides pour l'instant : une émission fiable de marqueurs mot-par-mot
# par le LLM n'a pas été validée, mieux vaut un contrat honnête qu'un champ
# qui prétend faire quelque chose qu'il ne fait pas encore.
_PACE_BY_STANCE = {
    "contradict": "slow",
    "recommend":  "slow",
    "challenge":  "measured",
    "caution":    "measured",
    "validate":   "standard",
    "clarify":    "standard",
}


def _speech_profile_for(stance: str) -> dict:
    return {"pace": _PACE_BY_STANCE.get(stance, "measured"), "emphasis": [], "pause_after": []}


def _call_mistral(prompt: str, max_tokens: int = 350, system: str = None) -> str:
    from mistralai import Mistral
    key = os.environ.get("MISTRAL_API_KEY")
    if not key:
        raise RuntimeError("MISTRAL_API_KEY manquante.")
    client = Mistral(api_key=key, timeout_ms=20_000)
    response = client.chat.complete(
        model="mistral-small-latest",
        max_tokens=max_tokens,
        messages=[{"role": "system", "content": system or _GABRIEL_SYSTEM}, {"role": "user", "content": prompt}],
    )
    return response.choices[0].message.content.strip()


def _fallback_utterance(text: str, stance: str = "clarify", next_question: str = "") -> dict:
    """Utilisée uniquement si l'appel Mistral échoue — un texte plat vaut
    mieux qu'une erreur affichée, mais reste conforme au contrat structuré
    pour que rien en aval (orchestrator, frontend) n'ait besoin de
    distinguer "réponse normale" et "réponse de secours"."""
    return {
        "display_text": text,
        "speech_text": text,
        "stance": stance,
        "tone": "calm",
        "strategic_observation": "",
        "next_question": next_question,
        "speech_profile": _speech_profile_for(stance),
    }


def _try_parse(raw: str, fallback_stance: str):
    """Tente d'extraire un utterance valide depuis une réponse brute — ne
    retombe JAMAIS sur un texte de secours ici (laisse l'appelant décider
    après une éventuelle nouvelle tentative). Retourne None si le JSON est
    absent, vide ou sans display_text exploitable."""
    try:
        start, end = raw.find('{'), raw.rfind('}') + 1
        # strict=False : speech_text est volontairement multi-ligne (une
        # phrase courte par ligne, voir _GABRIEL_SYSTEM) — Mistral renvoie
        # ces sauts de ligne littéralement dans la valeur JSON au lieu de
        # les échapper en \n, ce que json.loads() en mode strict rejette
        # ("Invalid control character"). Trouvé en conditions réelles :
        # sans ce paramètre, la synthèse finale retombait systématiquement
        # sur le texte de secours générique, jamais sur la vraie réponse.
        data = json.loads(raw[start:end], strict=False) if start >= 0 and end > start else {}
    except Exception:
        return None
    if not isinstance(data, dict) or not data.get("display_text"):
        return None

    display_text = str(data.get("display_text")).strip()
    speech_text  = str(data.get("speech_text") or display_text).strip()
    stance       = data.get("stance") if data.get("stance") in _PACE_BY_STANCE else fallback_stance
    tone         = data.get("tone") if data.get("tone") in ("calm", "direct", "reflective", "reassuring") else "calm"

    return {
        "display_text": display_text,
        "speech_text": speech_text,
        "stance": stance,
        "tone": tone,
        "strategic_observation": str(data.get("strategic_observation") or "").strip(),
        "next_question": str(data.get("next_question") or "").strip(),
        "speech_profile": _speech_profile_for(stance),
    }


def _render(prompt: str, fallback_text: str, fallback_stance: str, *, max_tokens: int = 350,
            system: str = None, fallback_next_question: str = "") -> dict:
    """Appel Mistral + parsing, avec une nouvelle tentative si la réponse est
    vide ou le JSON malformé — un appel LLM isolé peut échouer sans raison
    apparente (même constat que dans answer_extractor.py) ; un second essai
    avant de retomber sur le texte de secours évite qu'un aléa ponctuel du
    modèle ne se voie côté utilisateur."""
    for _attempt in range(2):
        try:
            raw = _call_mistral(prompt, max_tokens=max_tokens, system=system)
        except Exception:
            continue
        parsed = _try_parse(raw, fallback_stance)
        if parsed:
            return parsed
    return _fallback_utterance(fallback_text, fallback_stance, fallback_next_question)


def render_clarification(rejected_labels: list, dimension_question: str) -> dict:
    """Message quand la réponse était trop vague pour être exploitée —
    posture "clarify" systématique : il ne s'agit pas encore de juger,
    seulement d'obtenir une réponse exploitable."""
    labels = ", ".join(rejected_labels)
    prompt = (
        f'L\'utilisateur vient de répondre de façon trop vague sur : {labels}. '
        f"Relance-le pour obtenir un exemple concret, sans répéter mot pour mot "
        f"la question de base (\"{dimension_question}\"). Posture : clarify."
    )
    return _render(prompt, f"J'ai besoin d'un peu plus de précision sur ce point. {dimension_question}",
                    "clarify", max_tokens=280, fallback_next_question=dimension_question)


def render_transition(extracted_fields: dict, field_labels: dict, next_dimension_question: str) -> dict:
    """Message principal : prend position sur ce qui vient d'être dit (pas
    une validation automatique), puis pose la question de la dimension
    suivante."""
    if not extracted_fields:
        return _fallback_utterance(next_dimension_question, "clarify", next_dimension_question)
    learned = "; ".join(f"{field_labels.get(k, k)} : {v}" for k, v in extracted_fields.items())
    prompt = (
        f"Ce que l'utilisateur vient de préciser : {learned}.\n\n"
        f"Prends position sur cette information selon les règles de posture (clarify/validate/"
        f"caution/challenge/contradict/recommend) — pas une validation automatique. La majorité "
        f"des réponses restent simples : une reconnaissance courte suffit si rien ne justifie plus. "
        f"Termine par cette question : \"{next_dimension_question}\" (reformule-la naturellement, "
        f"ne la recopie pas mot pour mot)."
    )
    return _render(prompt, next_dimension_question, "validate", fallback_next_question=next_dimension_question)


def render_followup(extracted_fields: dict, field_labels: dict, missing_field_labels: list) -> dict:
    """Message quand la dimension en cours n'est PAS encore complète après
    cette réponse : cible UNIQUEMENT les champs encore manquants — jamais la
    question d'ouverture complète, qui redemanderait des points déjà
    répondus (trouvé en conditions réelles)."""
    missing = ", ".join(missing_field_labels)
    if extracted_fields:
        learned = "; ".join(f"{field_labels.get(k, k)} : {v}" for k, v in extracted_fields.items())
        prompt = (
            f"Ce que l'utilisateur vient de préciser : {learned}.\n\n"
            f"Prends position selon les règles de posture, puis pose une question naturelle et "
            f"courte pour obtenir UNIQUEMENT ce qui manque encore sur ce même sujet : {missing}. "
            f"Ne redemande jamais ce qui est déjà connu."
        )
    else:
        prompt = (
            f"Pose une question naturelle et courte (posture clarify) pour obtenir ces informations "
            f"encore manquantes sur le sujet en cours : {missing}."
        )
    return _render(prompt, f"Encore un point à préciser sur ce sujet : {missing}.", "clarify")


_COMPLETION_SYSTEM = _GABRIEL_SYSTEM + """

RÈGLE SUPPLÉMENTAIRE POUR CETTE SYNTHÈSE FINALE :
Ce n'est pas un résumé de catégories. C'est le moment où un consultant, après
un vrai entretien, livre sa première lecture — storytelling stratégique
complet : le point de départ, ce qui a construit l'entreprise jusqu'ici, la
tension actuelle, le verrou qui limite la suite, et la prochaine étape
logique. Nomme des faits précis tirés du contexte fourni (jamais génériques,
jamais inventés). Posture généralement "recommend" ou "challenge" — c'est le
moment de trancher, pas de rester prudent. display_text : 4 à 7 phrases.
speech_text : la même idée, en phrases courtes rythmées. next_question doit
donner envie de voir la suite — jamais la formule mécanique "vous pouvez
lancer la génération de la stratégie"."""


def render_completion(known_fields: dict) -> dict:
    """Message final quand toutes les dimensions obligatoires sont couvertes
    — une vraie synthèse personnelle générée à partir du contexte réel,
    jamais un texte fixe (un texte identique à chaque entretien, quel que
    soit le business, ne peut jamais donner l'impression "il m'a compris")."""
    lines = "\n".join(
        f"- {FIELD_LABEL_BY_KEY.get(k, k)} : {v}" for k, v in known_fields.items() if v
    )
    prompt = (
        f"Voici tout ce que vous savez de cette entreprise, recueilli pendant l'entretien :\n{lines}\n\n"
        "Livre ta première lecture — storytelling stratégique complet, pas un inventaire."
    )
    fallback_text = (
        "Je comprends maintenant l'essentiel de votre entreprise — sa vision, "
        "son modèle économique, ses ressources, ses contraintes, son historique "
        "et son objectif actuel. Vous pouvez lancer la génération de la "
        "stratégie, ou préciser encore certains points si vous le souhaitez."
    )
    # 260 tokens s'est révélé trop court en conditions réelles : une synthèse
    # dense en français dépasse facilement cette limite et se coupait au
    # milieu d'une phrase, visible par l'utilisateur.
    return _render(prompt, fallback_text, "recommend", max_tokens=520, system=_COMPLETION_SYSTEM)
