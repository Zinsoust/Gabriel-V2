# ═══════════════════════════════════════════════════════════════════════════
# LE CRÉATEUR — Moteur de création stratégique (pipeline)
#
# Ce module est le CŒUR de l'architecture décrite dans le brief : le LLM n'est
# plus le cerveau, il est l'écrivain. Le cerveau, c'est cette suite d'étapes.
#
# Le Créateur ne rédige jamais immédiatement. Il suit une méthode :
#
#   Observation → Compréhension → Construction → Recherche → Planification
#   → Rédaction → Critique → Optimisation → Validation → Livraison
#
# Chaque étape est un MOTEUR spécialisé (un module, une responsabilité) :
#   intent.py        → comprendre ce que l'utilisateur veut vraiment
#   context.py       → assembler tout le contexte Gabriel (jamais redemandé)
#   emotion.py       → déterminer l'expérience émotionnelle visée
#   knowledge.py     → sélectionner UNIQUEMENT les RAG utiles
#   planning.py      → construire le plan du contenu avant d'écrire
#   writing.py       → le LLM exécute le plan (il n'improvise plus)
#   dialectic.py     → penser CONTRE soi-même (pourquoi ce texte échouerait ?)
#   optimization.py  → corriger seulement les points faibles
#   quality.py       → validation finale + auto-évaluation chiffrée
#
# Extensible par conception : ajouter un moteur = l'ajouter à STAGES. Le cœur
# (run) ne change jamais. Même discipline que le Psychologue et le Stratège.
# ═══════════════════════════════════════════════════════════════════════════

import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass
class CreationContext:
    """L'objet qui traverse tout le pipeline. Chaque moteur lit ce dont il a
    besoin et écrit son résultat ici — jamais d'état caché ailleurs. C'est ce
    qui rend le pipeline lisible et extensible : on voit tout ce qui a été
    produit, étape par étape."""

    # ── Entrée (fournie par la route /creator/generate) ──────────────────────
    user_request: str = ""
    content_type: str = "hooks"
    channel: str = ""
    tone: str = ""
    emotion: str = ""            # émotion cible choisie (facultative)
    objective: str = ""
    creativity: int = 50         # 0-100 (curseur « niveau de créativité »)
    persona: Optional[dict] = None
    psycho_data: Dict[str, Any] = field(default_factory=dict)
    strategy: Dict[str, Any] = field(default_factory=dict)
    business_context: Dict[str, Any] = field(default_factory=dict)
    generate_variant: bool = False

    # ── Produit par les moteurs, dans l'ordre du pipeline ────────────────────
    intent: Optional[dict] = None              # Intent Engine
    recommended_emotions: Optional[list] = None  # Emotion Engine (proposition)
    rags_used: Optional[list] = None           # Knowledge Engine
    rag_context: str = ""
    plan: Optional[dict] = None                # Planning Engine
    draft: Optional[dict] = None               # Writing Engine (premier jet)
    critique: Optional[dict] = None            # Dialectic Engine
    scores: Optional[dict] = None              # Auto-évaluation
    quality: Optional[dict] = None             # Quality Engine (checklist)
    final: Optional[dict] = None               # Texte livré (après optimisation)
    variant: Optional[dict] = None             # Variante éventuelle

    # ── Journal d'exécution (temps par étape — le brief insiste dessus) ──────
    trace: List[dict] = field(default_factory=list)

    def note(self, stage: str, seconds: float, detail: str = "") -> None:
        self.trace.append({"stage": stage, "seconds": round(seconds, 2), "detail": detail})

    def temperature(self) -> float:
        """Traduit le niveau de créativité (0-100) en température LLM.
        50 → ~0.5 (équilibré). 0 → 0.15 (sobre, sûr). 100 → 0.95 (audacieux)."""
        c = max(0, min(100, int(self.creativity or 50)))
        return round(0.15 + (c / 100.0) * 0.80, 2)

    def total_seconds(self) -> float:
        return round(sum(t["seconds"] for t in self.trace), 2)


# Un moteur = une fonction qui reçoit le contexte et le fait avancer (mutation
# en place). Signature volontairement minimale pour rester composable.
Stage = Callable[[CreationContext], None]


# Libellés lisibles par étape — pour la progression en direct côté interface.
# On montre Gabriel en train de réfléchir, étape par étape, au lieu d'une barre
# générique : l'attente devient un moment où l'on voit le moteur travailler.
STAGE_LABELS = {
    "intent":       "Gabriel comprend votre intention…",
    "context":      "Gabriel rassemble tout votre contexte…",
    "emotion":      "Gabriel choisit l'expérience émotionnelle…",
    "knowledge":    "Gabriel puise dans son expertise éditoriale…",
    "planning":     "Gabriel construit le plan du contenu…",
    "writing":      "Gabriel rédige votre contenu…",
    "dialectic":    "Gabriel critique son propre texte…",
    "optimization": "Gabriel renforce les points faibles…",
    "quality":      "Gabriel valide la qualité finale…",
}


class CreationPipeline:
    """Orchestrateur. Ne contient AUCUNE logique métier propre à un moteur : il
    les appelle dans l'ordre, mesure le temps, et gère la boucle d'auto-
    amélioration (si l'auto-évaluation est trop basse, on relance une passe
    d'optimisation). Si une règle métier doit changer, elle change dans le
    moteur concerné — jamais ici."""

    def __init__(self, stages: Optional[List[tuple]] = None,
                 quality_threshold: int = 80, max_optim_passes: int = 1):
        # stages : liste ordonnée de (nom, fonction). Par défaut, le pipeline
        # complet est assemblé par build_default_pipeline() plus bas.
        self.stages = stages if stages is not None else _default_stages()
        self.quality_threshold = quality_threshold
        self.max_optim_passes = max_optim_passes

    def run(self, ctx: CreationContext, on_stage=None) -> CreationContext:
        # on_stage(name, label, progress_pct) est appelé AVANT chaque étape —
        # c'est ce qui alimente la progression en direct côté interface.
        #
        # PARALLÉLISME — mesuré en conditions réelles : le pipeline séquentiel
        # prenait ~93 s. Or certaines étapes ne dépendent pas les unes des
        # autres et attendaient pour rien :
        #   • knowledge (RAG, ~10 s) ne lit ni l'intention ni le plan → il peut
        #     tourner PENDANT intent/context/emotion.
        #   • dialectic (critique, ~12 s) et le calcul des scores lisent tous
        #     deux le même brouillon sans se lire l'un l'autre.
        # Le gain est du temps d'attente pur : aucune étape n'est supprimée,
        # la qualité est strictement identique.
        total = len(self.stages)
        pool = ThreadPoolExecutor(max_workers=2)
        knowledge_future = None
        try:
            for i, (name, fn) in enumerate(self.stages):
                # Le RAG démarre en fond dès le début du pipeline.
                if name == "knowledge":
                    knowledge_future = pool.submit(self._timed, ctx, name, fn)
                    continue

                # planning est le premier consommateur du RAG : on l'attend ici.
                if name == "planning" and knowledge_future is not None:
                    knowledge_future.result()
                    knowledge_future = None

                if on_stage:
                    try:
                        on_stage(name, STAGE_LABELS.get(name, name), round(i / total * 100))
                    except Exception:
                        pass
                self._timed(ctx, name, fn)
        finally:
            if knowledge_future is not None:
                try:
                    knowledge_future.result()
                except Exception:
                    pass
            pool.shutdown(wait=True)

        # ── Boucle d'auto-amélioration ───────────────────────────────────────
        # Après la première validation, si un score clé est sous le seuil, on
        # relance optimisation → qualité, quelques fois au maximum. C'est ce qui
        # distingue « un consultant qui se relit » d'« un LLM qui répond une fois ».
        passes = 0
        while (self._needs_improvement(ctx) and passes < self.max_optim_passes):
            passes += 1
            for name, fn in self.stages:
                if name in ("optimization", "quality"):
                    t0 = time.time()
                    try:
                        fn(ctx)
                        ctx.note(f"{name}#{passes+1}", time.time() - t0)
                    except Exception as e:
                        ctx.note(f"{name}#{passes+1}", time.time() - t0, detail=f"erreur: {e}")

        return ctx

    def _timed(self, ctx: CreationContext, name: str, fn) -> None:
        """Exécute un moteur en mesurant son temps. Un moteur qui échoue ne fait
        pas tomber toute la création : on le journalise et on continue avec ce
        qu'on a — la rédaction prime sur les étapes d'affinage."""
        t0 = time.time()
        try:
            fn(ctx)
            ctx.note(name, time.time() - t0)
        except Exception as e:
            ctx.note(name, time.time() - t0, detail=f"erreur: {e}")

    def _needs_improvement(self, ctx: CreationContext) -> bool:
        if not ctx.scores:
            return False
        # On relance tant qu'un score structurant reste sous le seuil.
        keys = ("persuasion", "clarte", "emotion", "coherence_strategique", "originalite")
        low = [k for k in keys if isinstance(ctx.scores.get(k), (int, float)) and ctx.scores[k] < self.quality_threshold]
        return bool(low)


def _default_stages() -> List[tuple]:
    """Assemble le pipeline complet. Import différé pour éviter les cycles et
    pour que le pipeline se charge même si un moteur a un souci d'import."""
    from agents.creation import (
        intent, context, emotion, knowledge, planning,
        writing, dialectic, optimization, quality,
    )
    return [
        ("intent",       intent.run),        # Compréhension
        ("context",      context.run),       # Construction du contexte
        ("emotion",      emotion.run),        # Expérience émotionnelle
        ("knowledge",    knowledge.run),      # Recherche (RAG ciblés)
        ("planning",     planning.run),       # Planification
        ("writing",      writing.run),        # Rédaction (le LLM écrit)
        ("dialectic",    dialectic.run),      # Critique (penser contre soi)
        ("optimization", optimization.run),   # Optimisation ciblée
        ("quality",      quality.run),        # Validation + auto-évaluation
    ]


def create(on_stage=None, **kwargs) -> CreationContext:
    """Point d'entrée pratique : construit le contexte, lance le pipeline
    complet, renvoie le contexte final (dont ctx.final = le texte livré)."""
    ctx = CreationContext(**{k: v for k, v in kwargs.items() if k in CreationContext.__dataclass_fields__})
    return CreationPipeline().run(ctx, on_stage=on_stage)


def generate_result(on_stage=None, **kwargs) -> dict:
    """Lance le pipeline ET met le résultat au FORMAT attendu par l'interface
    (le même contrat que le Créateur historique : writing_brief, content,
    full_text, quality_check…), plus des bonus de transparence (auto-évaluation,
    trace du pipeline). C'est ce que la route /creator/generate appelle.

    En cas de production vide/illisible, lève une exception → la route bascule
    sur le Créateur historique (repli). Aucune régression possible."""
    ctx = create(on_stage=on_stage, **kwargs)
    final = ctx.final or ctx.draft or {}
    if not final or final.get("parse_error") or final.get("success") is False:
        raise RuntimeError("pipeline: contenu illisible")

    fmt_key = (ctx.content_type or "hooks").lower().replace("-", "_").replace(" ", "_")

    # full_text lisible — réutilise l'extracteur du Créateur historique.
    try:
        from agents.createur import Createur, _FORMAT_RAG
        agent = Createur()
        full_text = agent._extract_full_text(final, fmt_key)
    except Exception:
        full_text = ""
        _FORMAT_RAG = {}

    rags_used_list = [
        {"name": r,
         "type": "format" if r in _FORMAT_RAG.get(fmt_key, []) else "tone",
         "reason": "sélectionné automatiquement"}
        for r in (ctx.rags_used or [])
    ]

    digest = (ctx.business_context or {}).get("_digest", {})
    intent = ctx.intent or {}
    writing_brief = {
        "format":         ctx.content_type,
        "channel":        ctx.channel,
        "objective":      ctx.objective or intent.get("objectif", ""),
        "target_persona": (ctx.persona or {}).get("nom", "") if isinstance(ctx.persona, dict) else "",
        "main_angle":     digest.get("positionnement", ""),
        "emotion_cible":  ctx.emotion or "",
    }

    return {
        "writing_brief": writing_brief,
        "rags_used":     rags_used_list,
        "content":       final,
        "full_text":     full_text,
        "variant":       ctx.variant or {},
        "quality_check": ctx.quality or {},
        "content_type":  ctx.content_type,
        "success":       True,
        # ── Transparence : la réflexion du moteur (interne, mais exposée) ──
        "auto_eval":       ctx.scores or {},
        "pipeline_trace":  ctx.trace,
        "pipeline_seconds": ctx.total_seconds(),
    }
