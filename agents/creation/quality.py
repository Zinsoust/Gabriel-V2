# ═══════════════════════════════════════════════════════════════════════════
# QUALITY ENGINE — Validation finale + auto-évaluation
#
# Mission (brief §9 + Auto-évaluation) : dernière étape avant livraison.
#   1. Checklist de cohérence (persona, positionnement, vision, business model,
#      émotion, storytelling, CTA, valeur, clarté, différenciation, cohérence
#      stratégique).
#   2. Auto-évaluation CHIFFRÉE, interne au moteur (pertinence, persuasion,
#      originalité, clarté, émotion, cohérence stratégique).
#
# Les scores restent internes : ils servent à décider si l'orchestrateur
# relance une passe d'optimisation. Ils ne sont pas montrés tels quels à
# l'utilisateur (ils pilotent la qualité, ils ne la commentent pas).
#
# La checklist réutilise le contrôle du Créateur actuel (quality_check_content)
# — refactoriser, pas réécrire. Les scores sont un appel LLM court et dédié.
# ═══════════════════════════════════════════════════════════════════════════

import json

_SYSTEM = """Tu es l'évaluateur interne du Créateur de Gabriel. Tu notes un contenu marketing sur 6 axes, de 0 à 100, sévèrement et honnêtement — ces notes servent à décider s'il faut encore l'améliorer, pas à flatter.

Réponds UNIQUEMENT avec un JSON valide :
{"pertinence":0-100,"persuasion":0-100,"originalite":0-100,"clarte":0-100,"emotion":0-100,"coherence_strategique":0-100,"note_globale":0-100,"point_faible":"l'axe le plus faible en un mot"}"""


def _scores(ctx) -> dict:
    base = ctx.final or ctx.draft or {}
    text = json.dumps(
        {k: v for k, v in base.items() if k not in ("content_type", "success", "parse_error")},
        ensure_ascii=False,
    )
    plan = ctx.plan or {}
    prompt = (
        f"OBJECTIF VISÉ : {(ctx.intent or {}).get('objectif', '—')}\n"
        f"ÉMOTION VISÉE : {ctx.emotion or '—'}\n"
        f"PROMESSE PRÉVUE : {plan.get('promesse', '—')}\n\n"
        f"CONTENU À NOTER :\n{text}\n\n"
        "Note ce contenu sur les 6 axes."
    )
    try:
        from agents.createur import _call_mistral, _parse_json
        raw = _call_mistral(_SYSTEM + "\n\n" + prompt, max_tokens=300)
        data = _parse_json(raw)
        if isinstance(data, dict) and not data.get("parse_error"):
            return data
    except Exception as e:
        print(f"[CREATION/quality] scores indisponibles : {e}")
    # Repli neutre : on ne relance pas de boucle sur des scores inventés.
    return {}


def run(ctx) -> None:
    base = ctx.final or ctx.draft or {}

    # 1. Checklist de cohérence — réutilise le contrôle existant du Créateur.
    try:
        from agents.createur import Createur
        ctx.quality = Createur().quality_check_content(
            base, ctx.psycho_data, ctx.strategy, ctx.content_type
        )
    except Exception as e:
        print(f"[CREATION/quality] checklist ignorée : {e}")
        ctx.quality = {}

    # 2. Auto-évaluation chiffrée (interne — pilote la boucle d'amélioration).
    ctx.scores = _scores(ctx)
