# ═══════════════════════════════════════════════════════════════════════════
# CONTEXT BUILDER ARCHITECTURE — Tone Renderer (V1.1)
#
# Rôle unique : transformer une décision logique (dimension traitée, champs
# appris, dimension suivante) en message affiché à l'utilisateur. Ne décide
# jamais quoi demander (Question Planner) et n'extrait jamais d'information
# (Answer Extractor) — uniquement la formulation.
#
# Règles de ton (brief) :
#   - Majordome stratégique élégant, jamais théâtral ("permettez-moi
#     humblement..." est interdit).
#   - Ne pas féliciter mécaniquement chaque réponse ("Très bien !",
#     "Excellent !", "Formidable !") — accuser réception intelligemment en
#     montrant la CONSÉQUENCE stratégique de ce qui vient d'être dit.
#   - Confiance, pas lien affectif artificiel : Gabriel ne prétend jamais
#     ressentir des émotions.
# ═══════════════════════════════════════════════════════════════════════════

import os
from agents.context_builder.schema import FIELD_LABEL_BY_KEY

_TONE_SYSTEM = """Tu es Gabriel, conseiller stratégique. Le registre : l'assurance tranquille d'un avocat d'affaires qui a déjà gagné le dossier avant même la plaidoirie — direct, incisif, jamais théâtral, jamais pompeux. Pense au sang-froid d'un closer qui sait exactement où la conversation mène, pas à un assistant poli qui coche des cases.

RÈGLES ABSOLUES :
1. Ne jamais commencer par "Permettez-moi", "Monsieur", ou toute formule obséquieuse.
2. Ne jamais féliciter mécaniquement ("Très bien !", "Excellent !", "Formidable !", "Super projet !").
3. À la place, nomme la CONSÉQUENCE stratégique de ce qui vient d'être dit — avec tranchant, comme si tu venais de repérer la faille ou la force dans leur raisonnement avant eux. Une phrase qui prouve que tu as déjà trois coups d'avance, pas qui valide poliment.
4. Assurance, pas arrogance : tu ne doutes jamais de ton analyse, mais tu restes au service de l'utilisateur — jamais condescendant, jamais méprisant.
5. Phrases courtes et affirmatives. Pas de conditionnel timide ("il semblerait que", "peut-être que") — tu affirmes.
6. Termine toujours par la question suivante, posée avec la même assurance (pas une supplique, une évidence qu'il faut trancher).
7. 2 à 4 phrases maximum.
8. Quand ça a du sens, ne te contente pas d'enchaîner poliment vers le sujet suivant — questionne d'abord ce qui vient d'être dit, comme un consultant qui creuse avant de noter. "Pourquoi ce choix ?", "Est-ce stratégique ou juste l'histoire de l'entreprise ?", "Ça, c'est un choix ou une contrainte ?" — une vraie relance qui prouve que tu écoutes, pas un enchaînement mécanique de questions préparées à l'avance.

Exemple de ce qu'il NE FAUT PAS faire :
"Super, merci pour ces informations ! Passons à la question suivante."

Exemple de ce qu'il NE FAUT PAS faire non plus (trop mou, trop prudent) :
"Je comprends mieux, c'est intéressant. Pourriez-vous peut-être préciser un peu plus comment vous gagnez de l'argent ?"

Exemple de ce qu'il FAUT faire :
"Votre avantage, ce n'est pas la technologie — c'est vous, dans la pièce. Ça se vend cher, mais ça ne scale pas seul. Comment cette expertise se traduit-elle en euros aujourd'hui, et à quel prix ?"

Exemple avec relance qui creuse avant d'enchaîner :
"Tout repose sur vous seule depuis le début. Est-ce un choix — vous vouliez garder la main — ou personne d'autre n'a jamais pris le relais ? Et concrètement, sur quelles ressources pouvez-vous vous appuyer aujourd'hui : budget, équipe, temps disponible ?"
"""


def _call_mistral(prompt: str, max_tokens: int = 200, system: str = None) -> str:
    from mistralai import Mistral
    key = os.environ.get("MISTRAL_API_KEY")
    if not key:
        raise RuntimeError("MISTRAL_API_KEY manquante.")
    client = Mistral(api_key=key, timeout_ms=20_000)
    response = client.chat.complete(
        model="mistral-small-latest",
        max_tokens=max_tokens,
        messages=[{"role": "system", "content": system or _TONE_SYSTEM}, {"role": "user", "content": prompt}],
    )
    return response.choices[0].message.content.strip()


def render_clarification(rejected_labels: list, dimension_question: str) -> str:
    """Message quand la réponse était trop vague pour être exploitée."""
    labels = ", ".join(rejected_labels)
    prompt = (
        f'L\'utilisateur vient de répondre de façon trop vague sur : {labels}. '
        f"Relance-le gentiment en lui demandant un exemple concret, sans répéter "
        f"mot pour mot la question de base (\"{dimension_question}\")."
    )
    try:
        return _call_mistral(prompt)
    except Exception:
        return f"J'ai besoin d'un peu plus de précision sur ce point. {dimension_question}"


def render_transition(extracted_fields: dict, field_labels: dict, next_dimension_question: str) -> str:
    """Message principal : accuse réception intelligemment de ce qui vient
    d'être appris, puis pose la question de la dimension suivante."""
    if extracted_fields:
        learned = "; ".join(f"{field_labels.get(k, k)} : {v}" for k, v in extracted_fields.items())
        prompt = (
            f"Ce que l'utilisateur vient de préciser : {learned}.\n\n"
            f"Montre que tu as compris la conséquence stratégique de cette information "
            f"(pas juste une validation polie), puis enchaîne naturellement avec cette "
            f"question : \"{next_dimension_question}\""
        )
        try:
            return _call_mistral(prompt)
        except Exception:
            return next_dimension_question
    return next_dimension_question


def render_followup(extracted_fields: dict, field_labels: dict, missing_field_labels: list) -> str:
    """Message quand la dimension en cours n'est PAS encore complète après
    cette réponse : accuse réception de ce qui vient d'être appris, puis
    cible UNIQUEMENT les champs encore manquants de cette même dimension —
    jamais la question d'ouverture complète, qui redemanderait des points
    déjà répondus. Trouvé en conditions réelles : une réponse partielle
    ("offer" et "target" connus, "format" manquant) faisait reposer toute la
    question d'identité, y compris ce qui était déjà su."""
    missing = ", ".join(missing_field_labels)
    if extracted_fields:
        learned = "; ".join(f"{field_labels.get(k, k)} : {v}" for k, v in extracted_fields.items())
        prompt = (
            f"Ce que l'utilisateur vient de préciser : {learned}.\n\n"
            f"Montre que tu as compris la conséquence stratégique de cette information "
            f"(pas juste une validation polie), puis pose une question naturelle et courte "
            f"pour obtenir UNIQUEMENT ce qui manque encore sur ce même sujet : {missing}. "
            f"Ne redemande jamais ce qui est déjà connu."
        )
    else:
        prompt = (
            f"Pose une question naturelle et courte pour obtenir ces informations "
            f"encore manquantes sur le sujet en cours : {missing}."
        )
    try:
        return _call_mistral(prompt)
    except Exception:
        return f"Encore un point à préciser sur ce sujet : {missing}."


_COMPLETION_SYSTEM = _TONE_SYSTEM + """

RÈGLE SUPPLÉMENTAIRE POUR CETTE SYNTHÈSE FINALE :
Ce n'est pas un résumé de catégories ("j'ai compris votre vision, votre modèle
économique..."). C'est le moment où un consultant, après un vrai entretien,
livre sa première lecture — ce qui structure réellement cette entreprise, la
tension centrale qu'il a repérée. Nomme des faits précis tirés du contexte
fourni (jamais génériques, jamais inventés). 3 à 5 phrases. Termine par une
phrase qui donne envie de voir la suite — jamais la formule mécanique "vous
pouvez lancer la génération de la stratégie"."""


def render_completion(known_fields: dict) -> str:
    """Message final quand toutes les dimensions obligatoires sont couvertes —
    une vraie synthèse personnelle générée à partir du contexte réel, jamais
    un texte fixe. Un texte identique à chaque entretien, quel que soit le
    business, ne peut jamais donner l'impression "il m'a compris" — trouvé
    en relisant le produit fini : la version précédente ne changeait jamais,
    peu importe ce qui avait été dit."""
    lines = "\n".join(
        f"- {FIELD_LABEL_BY_KEY.get(k, k)} : {v}" for k, v in known_fields.items() if v
    )
    prompt = (
        f"Voici tout ce que vous savez de cette entreprise, recueilli pendant l'entretien :\n{lines}\n\n"
        "Livre ta première lecture — ce qui structure vraiment cette entreprise, "
        "la tension ou le pilier central que tu repères. Utilise les faits précis "
        "ci-dessus, rien d'autre."
    )
    try:
        # 260 tokens s'est révélé trop court en conditions réelles : une
        # synthèse à 5 phrases denses en français dépasse facilement cette
        # limite et se coupait au milieu d'une phrase, visible par
        # l'utilisateur — mieux vaut de la marge qu'une réponse tronquée.
        return _call_mistral(prompt, max_tokens=420, system=_COMPLETION_SYSTEM)
    except Exception:
        return (
            "Je comprends maintenant l'essentiel de votre entreprise — sa vision, "
            "son modèle économique, ses ressources, ses contraintes, son historique "
            "et son objectif actuel. Vous pouvez lancer la génération de la "
            "stratégie, ou préciser encore certains points si vous le souhaitez."
        )
