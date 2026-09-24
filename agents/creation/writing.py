# ═══════════════════════════════════════════════════════════════════════════
# WRITING ENGINE — Le LLM écrit (et seulement ici)
#
# Mission (brief §6) : le LLM n'est plus le cerveau, il est l'écrivain. Il
# reçoit un brief extrêmement structuré — le plan (Planning), le contexte
# (Context), l'émotion (Emotion), les références (Knowledge), la discipline de
# ton et le format attendu — et il EXÉCUTE. Il n'improvise plus l'ossature :
# elle a déjà été décidée en amont.
#
# On réutilise les briques éprouvées du Créateur actuel (_SYSTEM_PROMPTS par
# format, build_writing_brief, disciplines de ton et d'émotion) : refactoriser,
# pas réécrire. La nouveauté est l'injection du PLAN dans le prompt.
# ═══════════════════════════════════════════════════════════════════════════


def _plan_block(plan: dict) -> str:
    if not plan:
        return ""
    lines = ["── PLAN À EXÉCUTER (ne pas réinventer, suivre ce plan) ──"]
    if plan.get("message_principal"): lines.append(f"Message principal : {plan['message_principal']}")
    if plan.get("promesse"):          lines.append(f"Promesse : {plan['promesse']}")
    if plan.get("angle"):             lines.append(f"Angle : {plan['angle']}")
    if plan.get("objections"):        lines.append(f"Objections à lever : {'; '.join(map(str, plan['objections']))}")
    if plan.get("preuves"):           lines.append(f"Preuves à utiliser : {'; '.join(map(str, plan['preuves']))}")
    if plan.get("fil_narratif"):      lines.append(f"Fil narratif : {plan['fil_narratif']}")
    if plan.get("cta"):               lines.append(f"CTA : {plan['cta']}")
    if plan.get("structure"):         lines.append(f"Structure : {' → '.join(map(str, plan['structure']))}")
    return "\n".join(lines) + "\n"


def _build_prompt(ctx) -> tuple:
    from agents.createur import (
        Createur, _get_tone_discipline, _get_emotion_directive, _SYSTEM_PROMPTS,
    )
    fmt_key = (ctx.content_type or "hooks").lower().replace("-", "_").replace(" ", "_")
    system_pmt = _SYSTEM_PROMPTS.get(fmt_key, _SYSTEM_PROMPTS["hooks"])

    agent = Createur()
    brief_text = agent.build_writing_brief(
        ctx.content_type, ctx.channel, ctx.tone, ctx.objective,
        ctx.psycho_data, ctx.strategy, ctx.persona, ctx.business_context, ctx.user_request,
    )

    tone_disc = _get_tone_discipline(ctx.tone or "")
    tone_block = (f"\n── DISCIPLINE DE TON ──\n{tone_disc}\n") if tone_disc else ""

    emo_disc = _get_emotion_directive(ctx.emotion or "")
    emo_block = (f"\n── ÉMOTION À FAIRE VIVRE ──\n{emo_disc}\n"
                 "Fais-la vivre par les faits, ne la nomme jamais.\n") if emo_disc else ""

    rag_block = (f"\n── RÉFÉRENCES RÉDACTIONNELLES ──\n{ctx.rag_context}\n") if ctx.rag_context else ""

    from agents.creation.fact_guard import SOURCE_RULE
    prompt = (
        f"{system_pmt}\n\n{SOURCE_RULE}\n"
        f"{tone_block}{emo_block}"
        f"\n{_plan_block(ctx.plan)}"
        f"{rag_block}\n"
        f"{brief_text}\n\n"
        "Rédige maintenant le contenu en suivant le plan ci-dessus. "
        "Chaque phrase doit pouvoir sortir de la bouche d'un humain. "
        "Utilise les mots réels de l'audience. Aucune formule IA-générique.\n"
        "JSON pur, sans markdown."
    )
    return prompt, system_pmt


def run(ctx) -> None:
    try:
        from agents.createur import _call_llm, _parse_json
        prompt, _ = _build_prompt(ctx)
        # Le niveau de créativité pilote la température : c'est à la RÉDACTION
        # qu'il compte le plus (le reste du pipeline reste déterministe).
        from agents.createur import CREATION_MAX_TOKENS
        raw = _call_llm(prompt, max_tokens=CREATION_MAX_TOKENS, temperature=ctx.temperature())
        draft = _parse_json(raw)
        draft["content_type"] = ctx.content_type
        draft["success"] = not draft.get("parse_error", False)
        ctx.draft = draft
        # Par défaut, le texte livré = le premier jet. La critique et
        # l'optimisation qui suivent le remplaceront s'il y a mieux à faire.
        ctx.final = draft
    except Exception as e:
        print(f"[CREATION/writing] échec de rédaction : {e}")
        ctx.draft = {"parse_error": True, "success": False, "content_type": ctx.content_type}
        ctx.final = ctx.draft
