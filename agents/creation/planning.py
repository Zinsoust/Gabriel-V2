# ═══════════════════════════════════════════════════════════════════════════
# PLANNING ENGINE — Le plan du contenu, AVANT d'écrire
#
# Mission (brief §5) : le LLM ne commence jamais à écrire sans plan. Ce moteur
# prépare l'ossature stratégique — message principal, promesse, angle,
# objections à lever, preuves, fil narratif, CTA, structure — à partir de
# l'intention, du contexte, de l'émotion visée et de la stratégie.
#
# C'est ici que se joue la différence avec « un LLM qui répond » : on décide
# QUOI dire et dans QUEL ordre avant de choisir COMMENT le dire.
# ═══════════════════════════════════════════════════════════════════════════

_SYSTEM = """Tu es le planificateur de contenu du Créateur de Gabriel. Tu ne rédiges PAS le contenu final — tu construis son plan stratégique, l'ossature qu'un rédacteur exécutera ensuite.

Sois TÉLÉGRAPHIQUE : chaque valeur tient en une ligne courte, pas de phrases rédigées. C'est une ossature de travail, pas un document.

Réponds UNIQUEMENT avec un JSON valide :
{"message_principal":"l'idée unique que le lecteur doit retenir","promesse":"ce que le contenu promet concrètement","angle":"l'angle d'attaque distinctif","objections":["objection réelle à lever","..."],"preuves":["preuve/argument concret","..."],"fil_narratif":"la progression en une phrase (accroche → ... → action)","cta":"l'action unique demandée","structure":["étape 1 du contenu","étape 2","..."]}"""


def run(ctx) -> None:
    intent = ctx.intent or {}
    digest = (ctx.business_context or {}).get("_digest", {})
    strat = ctx.strategy or {}

    # L'émotion visée oriente le plan (une accroche « urgence » ne se construit
    # pas comme une accroche « confiance »). On la nomme si elle est choisie.
    emotion_line = f"ÉMOTION À PROVOQUER : {ctx.emotion}\n" if ctx.emotion else ""

    prompt = (
        f"FORMAT : {ctx.content_type}\n"
        f"INTENTION : {intent.get('objectif', '—')}\n"
        f"AUDIENCE : {intent.get('audience') or digest.get('cible', '—')}\n"
        f"RÉSULTAT ATTENDU : {intent.get('resultat_attendu', '—')}\n"
        f"{emotion_line}"
        f"POSITIONNEMENT : {digest.get('positionnement') or strat.get('angle_positionnel', '—')}\n"
        f"DÉCISION STRATÉGIQUE : {digest.get('decision', '—')}\n"
        f"INSIGHT AUDIENCE : {digest.get('insight_audience', '—')}\n"
        f"FRUSTRATIONS : {', '.join(str(f) for f in (digest.get('frustrations') or [])) or '—'}\n"
        f"DÉSIRS : {', '.join(str(d) for d in (digest.get('desirs') or [])) or '—'}\n\n"
        "Construis le plan stratégique de ce contenu."
    )
    try:
        from agents.createur import _call_llm, _parse_json
        # 550 au lieu de 900 : le plan est une ossature, pas un texte. Mesuré
        # en conditions réelles, cette étape coûtait 20 s — l'essentiel du temps
        # partait à rédiger des phrases longues dont la rédaction n'a pas besoin.
        raw = _call_llm(_SYSTEM + "\n\n" + prompt, max_tokens=550)
        data = _parse_json(raw)
        if isinstance(data, dict) and not data.get("parse_error"):
            ctx.plan = data
            return
    except Exception as e:
        print(f"[CREATION/planning] plan minimal (repli) : {e}")
    # Repli : un plan minimal vaut mieux que pas de plan — la rédaction garde
    # un cap même si la planification a échoué.
    ctx.plan = {
        "message_principal": intent.get("objectif", ""),
        "promesse": intent.get("resultat_attendu", ""),
        "angle": intent.get("angle_pressenti", ""),
        "objections": [], "preuves": [],
        "fil_narratif": "", "cta": "", "structure": [],
    }
