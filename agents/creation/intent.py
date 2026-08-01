# ═══════════════════════════════════════════════════════════════════════════
# INTENT ENGINE — Comprendre ce que l'utilisateur veut VRAIMENT
#
# Mission (brief §1) : ne pas lire « je veux un post LinkedIn », mais
# comprendre : pourquoi ? pour quel objectif ? pour quelle audience ? quel
# résultat attendu ? Sortie = un objectif clair et exploitable.
#
# Un seul appel LLM, court : c'est de la compréhension, pas de la rédaction.
# Si la demande est vide (ex. l'utilisateur part d'une suggestion), on dérive
# l'intention du contexte déjà connu sans appeler le LLM.
# ═══════════════════════════════════════════════════════════════════════════

import json

from core.security import wrap_untrusted_content

_SYSTEM = """Tu es l'analyste d'intention du Créateur de Gabriel. À partir d'une demande de contenu et du contexte business, tu formules l'INTENTION RÉELLE — pas la surface.

Réponds UNIQUEMENT avec un JSON valide :
{"objectif":"le résultat concret visé, en une phrase","audience":"à qui s'adresse ce contenu précisément","resultat_attendu":"l'action ou le changement espéré chez le lecteur","angle_pressenti":"l'angle qui aurait le plus d'impact"}"""


def _heuristic(ctx) -> dict:
    biz = ctx.business_context or {}
    return {
        "objectif": ctx.objective or "Produire un contenu aligné sur la stratégie",
        "audience": biz.get("target") or biz.get("cible") or "l'audience cible de l'entreprise",
        "resultat_attendu": ctx.objective or "susciter une action concrète",
        "angle_pressenti": (ctx.strategy or {}).get("angle_positionnel", ""),
    }


def run(ctx) -> None:
    # Pas de demande libre → on dérive l'intention du contexte, sans LLM.
    if not (ctx.user_request or "").strip():
        ctx.intent = _heuristic(ctx)
        return

    biz = ctx.business_context or {}
    strat = ctx.strategy or {}
    prompt = (
        f"FORMAT demandé : {ctx.content_type}\n"
        f"CANAL : {ctx.channel or 'non précisé'}\n"
        f"OBJECTIF déclaré : {ctx.objective or 'non précisé'}\n"
        f"ACTIVITÉ : {biz.get('activite') or biz.get('offer') or '—'}\n"
        f"CIBLE : {biz.get('target') or biz.get('cible') or '—'}\n"
        f"ANGLE STRATÉGIQUE : {strat.get('angle_positionnel', '—')}\n\n"
        f"DEMANDE DE L'UTILISATEUR :\n{wrap_untrusted_content(ctx.user_request)}\n\n"
        "Formule l'intention réelle."
    )
    try:
        from agents.createur import _call_mistral, _parse_json
        raw = _call_mistral(_SYSTEM + "\n\n" + prompt, max_tokens=500)
        data = _parse_json(raw)
        if isinstance(data, dict) and not data.get("parse_error"):
            ctx.intent = data
            return
    except Exception as e:
        print(f"[CREATION/intent] repli heuristique : {e}")
    ctx.intent = _heuristic(ctx)
