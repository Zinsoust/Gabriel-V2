# ═══════════════════════════════════════════════════════════════════════════
# KNOWLEDGE ENGINE — Sélection intelligente des RAG
#
# Mission (brief §4) : ne JAMAIS charger tous les RAG. On n'appelle que les
# bases réellement utiles au format et à la tonalité en cours (ex. page SEO →
# SEO + copywriting + storytelling, pas tout le reste).
#
# Cette logique existe déjà et fonctionne dans le Créateur actuel
# (select_creator_rags + retrieve_creator_rag_context). Le Knowledge Engine
# la RÉUTILISE plutôt que la réécrire — refactorisation progressive, pas
# réécriture. Aucun nouvel appel LLM : le RAG fait une recherche vectorielle.
# ═══════════════════════════════════════════════════════════════════════════


def run(ctx) -> None:
    try:
        from agents.createur import Createur
        agent = Createur()
        rag_ctx, sources = agent.retrieve_creator_rag_context(
            ctx.content_type, ctx.tone, ctx.channel, ctx.psycho_data, ctx.strategy
        )
        ctx.rag_context = rag_ctx or ""
        ctx.rags_used = list(sources or [])
    except Exception as e:
        # Le RAG est un enrichissement, jamais un bloquant : sans lui, la
        # rédaction se fait quand même, seulement moins nourrie de références.
        ctx.rag_context = ""
        ctx.rags_used = []
        print(f"[CREATION/knowledge] RAG indisponible : {e}")
