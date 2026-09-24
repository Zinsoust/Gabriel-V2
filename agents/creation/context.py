# ═══════════════════════════════════════════════════════════════════════════
# CONTEXT ENGINE — Construction automatique du contexte
#
# Mission (brief §2) : rassembler TOUT ce que Gabriel sait déjà, pour que
# l'utilisateur n'ait jamais à répéter son entreprise, son audience, sa
# stratégie. Aucun appel LLM ici : c'est de l'assemblage. Les données sont
# déjà résolues en amont (route /creator/generate → _resolve_*), ce moteur
# les met en forme en un condensé exploitable par la planification et la
# rédaction.
# ═══════════════════════════════════════════════════════════════════════════


def _first(d: dict, *keys, default=""):
    for k in keys:
        v = (d or {}).get(k)
        if v:
            return v
    return default


def run(ctx) -> None:
    psycho = ctx.psycho_data or {}
    strat = ctx.strategy or {}
    biz = ctx.business_context or {}
    brief = psycho.get("brief") or {}
    psy = psycho.get("psychologie") or {}

    # Condensé lisible — les faits saillants, pas tout le JSON brut. C'est ce
    # que la planification et la critique reliront, donc on garde l'essentiel.
    digest = {
        "activite":        _first(biz, "activite", "activity", "offer", "offre"),
        "offre":           _first(biz, "offer", "offre", "offers_sold", "priority_offer"),
        "cible":           _first(biz, "target", "cible", "target_audience"),
        "positionnement":  _first(strat, "angle_positionnel", "positionnement"),
        "decision":        _first(strat, "decision_centrale", "executive_decision"),
        "insight_audience": _first(brief, "insight", "insight_cle", "qui", "synthese"),
        "frustrations":    (psy.get("frustrations") or [])[:3],
        "desirs":          (psy.get("desirs_caches") or [])[:3],
        "objectif_util":   ctx.objective or _first(ctx.intent or {}, "objectif"),
    }
    # On expose le condensé dans le contexte pour les étapes suivantes.
    ctx.business_context = {**biz, "_digest": digest}
