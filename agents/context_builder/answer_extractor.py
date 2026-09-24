# ═══════════════════════════════════════════════════════════════════════════
# CONTEXT BUILDER ARCHITECTURE — Answer Extractor (V1.1)
#
# Rôle unique : transformer UNE réponse libre de l'utilisateur en champs
# structurés pour LA dimension en cours. Ne décide jamais quelle dimension
# traiter (Question Planner) et ne rédige jamais de texte à afficher (Tone
# Renderer) — uniquement de l'extraction.
# ═══════════════════════════════════════════════════════════════════════════

import os

from core import llm_client as _llm
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


def _call_llm(prompt: str, system: str, max_tokens: int = 600) -> str:
    """Extraction structurée — passe par la couche fournisseur commune.

    Choix conservés tels quels, tous mesurés en conditions réelles :
    - palier profond : le palier rapide produisait trop de JSON vides sur des
      messages pourtant clairs ; une extraction ratée fait juste répéter la
      question sans explication, donc la fiabilité prime sur ~1,3 s de latence ;
    - température 0.1 : la tâche est déterministe (extraire ce qui est dit) ;
      une température plus haute produisait des JSON vides sans raison ;
    - pas de response_format JSON : mesuré ~60× plus lent (31 s contre 0,5 s)
      pour un résultat identique, le modèle respectant déjà le format demandé.
    """
    return _llm.complete_text(
        prompt,
        tier="deep",
        max_tokens=max_tokens,
        temperature=0.1,
        timeout_ms=30_000,
        retry=_llm.RETRY_SIMPLE,
        label="context_extraction",
        system=system,
    )


# Perdue par accident lors du renommage _call_mistral → _call_llm (commit
# bb17f4c) : la référence à _EXTRACT_SYSTEM à la ligne ci-dessous a survécu
# au refactor, pas sa définition. Le NameError qui en résultait était avalé
# par le `except Exception` de la boucle de retry — extract_answer() ne
# renvoyait donc plus jamais rien, silencieusement, sur chaque message qui
# n'était pas la toute première réponse de l'entretien (laquelle passe par
# extract_answer_freeform, resté correct). Trouvé en conditions réelles :
# le Stratège reposait indéfiniment la même question de la dimension
# "identity", quelle que soit la précision de la réponse donnée.
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
        return {"extracted": {}, "rejected_vague": [], "failed": False}

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
    extracted_raw, erreurs = _extraire_avec_reessai(prompt, _EXTRACT_SYSTEM, 600)
    if erreurs == _TENTATIVES:
        # Panne du modèle (quota, 403, réseau…) : ce n'est PAS une réponse
        # vide de l'utilisateur. Le signaler évite de reposer la question
        # comme s'il n'avait rien dit — la boucle observée le 13/09/2026.
        return {"extracted": {}, "rejected_vague": [], "failed": True}

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

    return {"extracted": extracted, "rejected_vague": rejected_vague, "failed": False}


_TENTATIVES = 2


def _extraire_avec_reessai(prompt: str, system: str, max_tokens: int):
    """Deux tentatives au plus. Renvoie (objet extrait, nombre d'appels en
    erreur) : un JSON vide renvoyé par le modèle n'est pas une erreur, une
    exception (API refusée, délai dépassé) en est une."""
    extracted_raw, erreurs = {}, 0
    for _attempt in range(_TENTATIVES):
        try:
            raw = _call_llm(prompt, system, max_tokens=max_tokens)
            start, end = raw.find('{'), raw.rfind('}') + 1
            extracted_raw = json.loads(raw[start:end]) if start >= 0 and end > start else {}
        except Exception as exc:
            erreurs += 1
            print(f"[CONTEXT_EXTRACTION] échec d'appel ({type(exc).__name__}) : {str(exc)[:160]}")
            extracted_raw = {}
        if extracted_raw:
            break
    return extracted_raw, erreurs


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

    extracted_raw, erreurs = _extraire_avec_reessai(prompt, _FREEFORM_EXTRACT_SYSTEM, 1200)
    if erreurs == _TENTATIVES:
        return {"extracted": {}, "rejected_vague": [], "failed": True}

    extracted, rejected_vague = _parse_extraction(extracted_raw, set(ALL_FIELD_KEYS))

    # Même garde-fou que extract_answer() : une présentation libre vide de
    # sens ne doit jamais se solder par un silence — voir le commentaire
    # équivalent plus haut pour le contexte de la découverte initiale.
    if not extracted and not rejected_vague and not _is_specific_enough(message):
        rejected_vague = ["votre présentation"]

    return {"extracted": extracted, "rejected_vague": rejected_vague, "failed": False}
