# ═══════════════════════════════════════════════════════════════════════════
# LE CRÉATEUR — Moteur de création stratégique (package)
#
# Architecture modulaire (brief) : le LLM est l'écrivain, le pipeline est le
# cerveau. Chaque moteur = un module, une responsabilité. On compose ici, on
# n'écrit pas de logique métier.
#
# Additif et non destructif : ce package RÉUTILISE le Créateur existant
# (agents/createur.py) pour tout ce qui marche déjà (RAG, brief, ton, émotion,
# contrôle qualité). Rien n'est déplacé, rien n'est cassé — refactorisation
# progressive, comme demandé.
#
# Usage :
#   from agents.creation import create, CreationContext, CreationPipeline
#   ctx = create(user_request="...", content_type="linkedin", tone="expert", ...)
#   texte_livre = ctx.final
# ═══════════════════════════════════════════════════════════════════════════

from agents.creation.pipeline import (
    CreationContext,
    CreationPipeline,
    create,
    generate_result,
)

__all__ = ["CreationContext", "CreationPipeline", "create", "generate_result"]
