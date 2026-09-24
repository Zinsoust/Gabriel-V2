# ═══════════════════════════════════════════════════════════════════════════
# OPTIMIZATION ENGINE — Corriger seulement les points faibles
#
# Mission (brief §8) : le système ne réécrit pas tout, il AMÉLIORE. Il prend le
# texte et la liste de faiblesses produite par le Dialectic Engine, et corrige
# uniquement ce qui doit l'être (hook, rythme, CTA, émotion, clarté,
# persuasion), en préservant ce qui fonctionne déjà.
#
# S'il n'y a rien à corriger (critique vide, verdict « livrable »), ce moteur
# ne touche à rien : pas d'appel LLM inutile, le premier jet est livré tel quel.
# Appelé aussi en boucle par l'orchestrateur quand l'auto-évaluation est basse.
# ═══════════════════════════════════════════════════════════════════════════

import json

_SYSTEM = """Tu es l'optimiseur du Créateur de Gabriel. On te donne un texte et la liste précise de ses faiblesses. Tu produis une version AMÉLIORÉE qui corrige ces faiblesses — sans tout réécrire, en gardant ce qui marche déjà, dans le MÊME format JSON que l'original.

Règles :
- Corrige uniquement les zones signalées.
- Ne change pas le format ni la structure JSON du texte fourni.
- Chaque correction doit être défendable : plus fort, plus clair, plus incarné.
- N'ajoute jamais de chiffre, d'étude, de source, de témoignage, de pseudo ou d'anecdote personnelle absent des données : reformule l'idée sans eux. Pour corriger un manque de « preuve », utilise les mots réels de l'audience, jamais un fait fabriqué.
- Si une faiblesse signale un fait inventé, retire-le et reformule sans emplacement entre crochets.

Réponds UNIQUEMENT avec le JSON du texte amélioré, même schéma que l'original, sans commentaire."""


def _weaknesses_to_fix(ctx) -> list:
    crit = ctx.critique or {}
    faiblesses = crit.get("faiblesses") or []
    # Seules les faiblesses CRITIQUES déclenchent une réécriture. Mesuré en
    # conditions réelles : cette étape coûte ~25 s (elle régénère tout le
    # contenu). La déclencher pour un défaut "moyen" — souvent cosmétique —
    # faisait payer cette attente à presque chaque création sans gain net.
    # Les défauts moyens restent visibles dans le regard critique affiché.
    return [f for f in faiblesses if f.get("gravite") == "critique"]


def run(ctx) -> None:
    base = ctx.final or ctx.draft
    if not base or base.get("parse_error"):
        return

    to_fix = _weaknesses_to_fix(ctx)
    # Aucune faiblesse CRITIQUE → on ne dépense pas un appel de ~25 s. Le
    # verdict global ne suffit pas à déclencher : le critique renvoie souvent
    # "a_ameliorer" pour des défauts mineurs, ce qui faisait payer la
    # réécriture complète à presque chaque création.
    if not to_fix:
        return

    schema_keys = [k for k in base.keys() if k not in ("content_type", "success", "parse_error")]
    text = json.dumps({k: base[k] for k in schema_keys}, ensure_ascii=False)
    faiblesses_txt = "\n".join(
        f"- [{f.get('gravite','?')}] {f.get('zone','')} : {f.get('probleme','')}" for f in to_fix
    ) or "- Renforcer l'accroche, l'émotion et le CTA."

    prompt = (
        f"FAIBLESSES À CORRIGER :\n{faiblesses_txt}\n\n"
        f"ÉMOTION À RENFORCER : {ctx.emotion or '—'}\n\n"
        f"TEXTE ORIGINAL (schéma à conserver) :\n{text}\n\n"
        "Produis la version améliorée (même schéma JSON)."
    )
    try:
        from agents.createur import _call_llm, _parse_json
        from agents.createur import CREATION_MAX_TOKENS
        from agents.creation.fact_guard import SOURCE_RULE
        raw = _call_llm(_SYSTEM + "\n\n" + SOURCE_RULE + "\n\n" + prompt, max_tokens=CREATION_MAX_TOKENS)
        improved = _parse_json(raw)
        if isinstance(improved, dict) and not improved.get("parse_error"):
            improved["content_type"] = ctx.content_type
            improved["success"] = True
            ctx.final = improved
    except Exception as e:
        # En cas d'échec, on garde la version précédente : jamais de régression.
        print(f"[CREATION/optimization] version conservée : {e}")
