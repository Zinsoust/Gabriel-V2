# ═══════════════════════════════════════════════════════════════════════════
# CONTEXT BUILDER ARCHITECTURE — Answer Extractor (V1.1)
#
# Rôle unique : transformer UNE réponse libre de l'utilisateur en champs
# structurés pour LA dimension en cours. Ne décide jamais quelle dimension
# traiter (Question Planner) et ne rédige jamais de texte à afficher (Tone
# Renderer) — uniquement de l'extraction.
# ═══════════════════════════════════════════════════════════════════════════

import os
import json
import re

from core.security import wrap_untrusted_content
from agents.context_builder.schema import DIMENSION_BY_KEY, CONTEXT_DIMENSIONS, ALL_FIELD_KEYS, FIELD_LABEL_BY_KEY

_VAGUE_PATTERNS = [
    "je sais pas", "je ne sais pas", "pas grand chose", "pas encore",
    "un peu de tout", "pas beaucoup", "rien de precis", "rien de précis",
    "pas vraiment", "pas trop", "aucune idee", "aucune idée", "on verra",
    "pas defini", "pas défini", "pas encore defini", "pas encore défini",
]


def _is_specific_enough(value: str) -> bool:
    """Rejette les réponses trop courtes ou trop génériques pour être
    exploitables — un champ rejeté reste "manquant" plutôt que d'être
    rempli avec une esquive."""
    v = value.strip().lower()
    if len(v.split()) < 2:
        return False
    return not any(p in v for p in _VAGUE_PATTERNS)


def _call_mistral(prompt: str, system: str, max_tokens: int = 600) -> str:
    from mistralai import Mistral
    key = os.environ.get("MISTRAL_API_KEY")
    if not key:
        raise RuntimeError("MISTRAL_API_KEY manquante.")
    # NE PAS ajouter response_format={"type":"json_object"} : mesuré à environ
    # 60x plus lent (31s contre 0.5s) sur ce projet pour un résultat identique
    # — le modèle respecte déjà le format JSON demandé dans le prompt. Parsing
    # manuel du JSON dans le texte, comme partout ailleurs dans Gabriel.
    #
    # mistral-small-latest a été mesuré ici même en conditions réelles :
    # taux d'échec (JSON vide {} sur un message pourtant clair) trop élevé
    # pour être fiable sur cette tâche. mistral-large-latest, testé sur le
    # même cas, s'est montré nettement plus fiable — le coût en latence
    # (~1.3s) est justifié : c'est le cœur de la compréhension de Gabriel,
    # une extraction ratée fait juste répéter la question sans explication.
    client = Mistral(api_key=key, timeout_ms=30_000)
    for attempt in range(2):
        try:
            response = client.chat.complete(
                model="mistral-large-latest",
                max_tokens=max_tokens,
                # Température basse : cette tâche est fondamentalement
                # déterministe (extraire ce qui est dit, rien de plus) — pas
                # besoin de créativité, et une température par défaut plus
                # haute a été observée, en conditions réelles, produire des
                # JSON vides sans raison sur des messages pourtant clairs.
                temperature=0.1,
                messages=[{"role": "system", "content": system}, {"role": "user", "content": prompt}],
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            status = getattr(e, 'status_code', None) or getattr(e, 'http_status', None)
            if attempt == 0 and status in (429, 529):
                import time; time.sleep(4); continue
            raise


_EXTRACT_SYSTEM = """Tu extrais des informations business structurées depuis un message en langage naturel.

RÈGLES STRICTES :
1. Extraire UNIQUEMENT ce qui est explicitement dit — ne jamais inférer ni inventer.
2. Si un champ n'est pas mentionné dans le message, ne pas l'inclure dans le JSON.
3. Les valeurs doivent être des phrases courtes et précises, pas des mots seuls.
4. Un seul message peut renseigner plusieurs champs à la fois — extrais tout ce qui est présent.

Réponds UNIQUEMENT avec un objet JSON valide, sans texte autour."""


def extract_answer(dimension_key: str, message: str, already_known: dict = None) -> dict:
    """Extrait les champs de la dimension donnée depuis un message libre.

    Retourne {"extracted": {field_key: value}, "rejected_vague": [field_keys]} —
    un champ "rejected_vague" reste manquant pour qu'on puisse redemander une
    réponse précise plutôt que d'accepter une esquive comme une vraie info.
    """
    dim = DIMENSION_BY_KEY.get(dimension_key)
    if not dim:
        return {"extracted": {}, "rejected_vague": []}

    already_known = already_known or {}
    field_lines = "\n".join(
        f'- {f["key"]} : {f["label"]}' for f in dim["fields"]
    )
    known_lines = "\n".join(
        f'- {k} : {v}' for k, v in already_known.items() if v
    ) or "(aucune information déjà connue pour cette dimension)"

    prompt = (
        f"Dimension actuelle : {dim['label']}\n\n"
        f"Champs à extraire (utiliser exactement ces clés) :\n{field_lines}\n\n"
        f"Déjà connu pour cette dimension :\n{known_lines}\n\n"
        f"Message de l'utilisateur à analyser :\n{wrap_untrusted_content(message)}\n\n"
        'Exemple de format de réponse : {"budget": "environ 1000 euros pour démarrer", "team": "seul pour le moment"}'
    )

    # Une seule tentative suffit dans la grande majorité des cas, mais un
    # appel LLM peut renvoyer un JSON vide sans raison apparente même avec
    # mistral-large-latest. Un message clair qui n'extrait toujours rien
    # après une nouvelle tentative n'est probablement pas un hasard — dans
    # ce cas seulement, on abandonne et on laisse l'appelant gérer.
    extracted_raw = {}
    for _attempt in range(2):
        try:
            raw = _call_mistral(prompt, _EXTRACT_SYSTEM)
            start, end = raw.find('{'), raw.rfind('}') + 1
            extracted_raw = json.loads(raw[start:end]) if start >= 0 and end > start else {}
        except Exception:
            extracted_raw = {}
        if extracted_raw:
            break

    valid_keys = {f["key"] for f in dim["fields"]}
    extracted, rejected_vague = _parse_extraction(extracted_raw, valid_keys)

    # Cas non couvert par la boucle ci-dessus : le message entier est une
    # esquive ("je sais pas", "on verra"...) et le LLM n'a — à raison — rien
    # extrait du tout (règle 2 du prompt : ne rien inventer). Sans ce garde-
    # fou, extracted ET rejected_vague restent vides, et l'orchestrateur
    # (qui ne déclenche la relance que si rejected_vague est non-vide) se
    # contente de répéter la question mot pour mot, sans jamais reconnaître
    # que l'utilisateur a répondu quelque chose. Trouvé en testant en
    # conditions réelles avec "je sais pas trop, on verra".
    if not extracted and not rejected_vague and not _is_specific_enough(message):
        rejected_vague = [dim["label"]]

    return {"extracted": extracted, "rejected_vague": rejected_vague}


def _parse_extraction(extracted_raw, valid_keys: set) -> tuple:
    """Logique de nettoyage partagée entre extract_answer (une dimension) et
    extract_answer_freeform (toutes les dimensions) : valide les clés,
    aplatit les listes en texte, filtre le vague. Retourne
    (extracted: dict, rejected_vague_labels: list)."""
    extracted, rejected_vague = {}, []
    for key, value in (extracted_raw.items() if isinstance(extracted_raw, dict) else []):
        if key not in valid_keys:
            continue
        # Certains champs invitent naturellement plusieurs éléments (actions
        # tentées, échecs, outils...) — le modèle répond alors par une liste
        # plutôt qu'une phrase, à raison. Trouvé en conditions réelles : la
        # dimension "Historique" échouait presque systématiquement (1/6)
        # parce que ces listes, pourtant correctes, étaient rejetées en bloc
        # faute d'accepter autre chose qu'une chaîne de caractères.
        if isinstance(value, list):
            value = "; ".join(str(item).strip() for item in value if str(item).strip())
        if not isinstance(value, str) or not value.strip():
            continue
        v = value.strip()
        if _is_specific_enough(v):
            extracted[key] = v
        else:
            rejected_vague.append(FIELD_LABEL_BY_KEY.get(key, key))
    return extracted, rejected_vague


_FREEFORM_EXTRACT_SYSTEM = """Tu extrais des informations business structurées depuis la présentation libre d'un dirigeant qui décrit son entreprise avec ses propres mots.

RÈGLES STRICTES :
1. Extraire UNIQUEMENT ce qui est explicitement dit — ne jamais inférer ni inventer.
2. Un champ non mentionné ne doit pas apparaître dans le JSON — ne jamais le deviner ou le compléter par défaut.
3. Les valeurs doivent être des phrases courtes et précises, pas des mots seuls.
4. Une présentation libre couvre souvent PLUSIEURS thèmes en même temps (l'offre, la cible, le modèle économique, la vision...) — extrais TOUT ce qui est identifiable, quel que soit le thème auquel ça appartient.
5. Ne force jamais une information dans un champ qui ne lui correspond pas exactement.

Réponds UNIQUEMENT avec un objet JSON valide, sans texte autour."""


def extract_answer_freeform(message: str, already_known: dict = None) -> dict:
    """Extraction d'ouverture d'entretien (brief section 2.1) : contrairement
    à extract_answer() qui cible UNE dimension, celle-ci scanne les 33 champs
    des 7 dimensions en un seul appel — pour qu'une présentation libre riche
    ("je vends du coaching individuel à des entrepreneures débordées, je
    veux construire...") renseigne plusieurs dimensions d'un coup au lieu
    d'être limitée au premier thème demandé.

    Retourne {"extracted": {field_key: value}, "rejected_vague": [labels]},
    même contrat que extract_answer()."""
    already_known = already_known or {}
    field_lines = "\n".join(
        f'- {f["key"]} : {f["label"]} (thème : {dim["label"]})'
        for dim in CONTEXT_DIMENSIONS for f in dim["fields"]
    )
    known_lines = "\n".join(
        f'- {k} : {v}' for k, v in already_known.items() if v
    ) or "(aucune information déjà connue)"

    prompt = (
        f"Tous les champs que Gabriel peut extraire :\n{field_lines}\n\n"
        f"Déjà connu :\n{known_lines}\n\n"
        f"Présentation libre de l'utilisateur à analyser :\n{wrap_untrusted_content(message)}\n\n"
        'Exemple de réponse couvrant plusieurs thèmes à la fois : '
        '{"offer": "coaching individuel pour entrepreneures", "target": "femmes entrepreneures débordées", '
        '"revenue_sources": "prestations ponctuelles facturées à la séance"}'
    )

    extracted_raw = {}
    for _attempt in range(2):
        try:
            raw = _call_mistral(prompt, _FREEFORM_EXTRACT_SYSTEM, max_tokens=1200)
            start, end = raw.find('{'), raw.rfind('}') + 1
            extracted_raw = json.loads(raw[start:end]) if start >= 0 and end > start else {}
        except Exception:
            extracted_raw = {}
        if extracted_raw:
            break

    extracted, rejected_vague = _parse_extraction(extracted_raw, set(ALL_FIELD_KEYS))

    # Même garde-fou que extract_answer() : une présentation libre vide de
    # sens ne doit jamais se solder par un silence — voir le commentaire
    # équivalent plus haut pour le contexte de la découverte initiale.
    if not extracted and not rejected_vague and not _is_specific_enough(message):
        rejected_vague = ["votre présentation"]

    return {"extracted": extracted, "rejected_vague": rejected_vague}
