# ═══════════════════════════════════════════════════════════════════════════
# DIALECTIC ENGINE — Penser CONTRE soi-même
#
# Mission (brief §7) — fonctionnalité fondamentale. Avant de livrer, le
# Créateur joue volontairement l'avocat du diable contre son propre texte :
#   Pourquoi ce texte pourrait-il échouer ?
#   Pourquoi personne ne cliquerait ?
#   Pourquoi cette accroche est-elle faible ?
#   Pourquoi cette émotion ne fonctionnerait pas ?
#   Pourquoi cette idée manque-t-elle de différenciation ?
#   Pourquoi pourrait-il sembler artificiel ?
#
# Ce n'est PAS une relecture polie : c'est une critique adverse, ciblée, qui
# produit une liste de faiblesses concrètes à corriger. C'est elle qui pilote
# l'optimisation qui suit.
# ═══════════════════════════════════════════════════════════════════════════

import json

_SYSTEM = """Tu es le critique adverse du Créateur de Gabriel. Ton rôle n'est pas de féliciter : c'est d'attaquer le texte pour révéler ses faiblesses réelles, comme le ferait un directeur de création exigeant. Sois précis et sans complaisance, mais juste.

Réponds UNIQUEMENT avec un JSON valide :
{"faiblesses":[{"zone":"hook|emotion|differenciation|preuve|cta|rythme|authenticite|clarte","probleme":"le défaut concret, en une phrase","gravite":"critique|moyen|mineur"}],"risque_principal":"la raison n°1 pour laquelle ce contenu pourrait ne pas marcher","verdict":"livrable|a_ameliorer"}"""


def run(ctx) -> None:
    if not ctx.draft or ctx.draft.get("parse_error"):
        ctx.critique = {"faiblesses": [], "risque_principal": "", "verdict": "livrable"}
        return

    draft_text = json.dumps(
        {k: v for k, v in ctx.draft.items() if k not in ("content_type", "success")},
        ensure_ascii=False,
    )
    plan = ctx.plan or {}
    prompt = (
        f"FORMAT : {ctx.content_type}\n"
        f"ÉMOTION VISÉE : {ctx.emotion or 'aucune imposée'}\n"
        f"PROMESSE PRÉVUE : {plan.get('promesse', '—')}\n"
        f"ANGLE PRÉVU : {plan.get('angle', '—')}\n\n"
        f"TEXTE À CRITIQUER :\n{draft_text}\n\n"
        "Attaque ce texte. Où est-il faible, générique, ou artificiel ? "
        "Pourquoi pourrait-il ne pas atteindre son objectif ?"
    )
    from agents.createur import _call_llm, _parse_json
    from core.critic import critic
    from core.critiques import CREATION_CRITIQUE

    ctx.critique = critic.review(
        CREATION_CRITIQUE, _SYSTEM + "\n\n" + prompt,
        call_llm=lambda p, max_tokens: _call_llm(p, max_tokens=max_tokens),
        parse_json=_parse_json, max_tokens=500,
    ).data
