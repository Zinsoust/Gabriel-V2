# ─── Gabriel — Orchestrateur multi-agents ────────────────────────────────────
#
# Deux pipelines indépendants :
#   run_psycho()   → Psychologue uniquement (commentaires → insights humains)
#   run_stratege() → Stratège uniquement   (insights + profil projet → décision)
#
# Chaque agent reçoit l'AnalysisContext, lit les contributions précédentes,
# dépose la sienne, retourne le contexte enrichi.

from agents.context      import AnalysisContext
from agents.psychologue  import Psychologue
from agents.stratege     import Stratege
from agents.createur     import Createur
from core.executor       import Executor
from core.planner        import default_planner
from agents.design_agent import compose as _design_compose


class Gabriel:

    def __init__(self):
        self.psychologue = Psychologue()
        self.stratege    = Stratege()
        self.createur    = Createur()
        # L'enchaînement des agents n'est plus écrit ici : il est déduit des
        # dépendances déclarées au registre, puis déroulé par l'exécuteur.
        # Les deux méthodes ci-dessous restent les points d'entrée publics et
        # rendent exactement le même contenu qu'avant.
        self.planner  = default_planner()
        self.executor = Executor()
        self.last_trace = None

    # ── Pipeline 1 : Analyse Psychologique ───────────────────────────────────

    def run_psycho(self, comments, video_context="", title="", progress_cb=None, partial_cb=None):
        """
        Analyse les commentaires et retourne les insights psychologiques.
        N'a pas besoin du profil projet — s'appuie uniquement sur les données audience.
        progress_cb(step: str, progress: int) — optionnel, appelé aux étapes clés.
        partial_cb(key: str, data: dict) — optionnel, appelé dès qu'un bloc de résultat
        (dashboard / personas / interpretation) est prêt, avant la fin complète du pipeline.
        """
        ctx = AnalysisContext(
            comments=comments,
            brain_context="",
            video_context=video_context,
            title=title,
        )
        ctx.progress_cb = progress_cb
        ctx.partial_cb  = partial_cb
        ctx.record_step(f"[GABRIEL] Pipeline psychologique — {len(comments)} commentaires")

        ctx, self.last_trace = self.executor.execute(
            self.planner.plan('psychologue'), ctx)

        ctx.record_step("[GABRIEL] Pipeline psychologique terminé")
        return ctx.to_response()

    # ── Pipeline 2 : Analyse Stratégique ─────────────────────────────────────

    def run_stratege(self, psycho_data, brain_context="", title="", memory_context=""):
        """
        Produit la stratégie à partir des insights psychologiques + profil projet.
        psycho_data : résultat de run_psycho() (dict plat).
        brain_context : profil projet formaté en texte.
        memory_context : cas similaires passés formatés (injecté dans le prompt).
        """
        ctx = AnalysisContext(
            comments=[],
            brain_context=brain_context,
            video_context="",
            title=title,
            memory_context=memory_context,
        )
        # Injecter les données psychologiques comme si Le Psychologue venait de tourner
        ctx.add('psychologue', psycho_data)
        ctx.record_step("[GABRIEL] Pipeline stratégique démarré")

        # Le rapport psychologique est déjà en main : le plan ne le rejoue pas.
        ctx, self.last_trace = self.executor.execute(
            self.planner.plan('stratege', available=('psychologue',)), ctx)

        ctx.record_step("[GABRIEL] Pipeline stratégique terminé")
        self._preview_design_agent(ctx)
        return ctx.to_response()

    def _preview_design_agent(self, ctx):
        """Observation temporaire : fait tourner le Design Agent (DESIGN_RUNTIME)
        sur la vraie sortie du Stratège et journalise sa décision, sans jamais
        toucher à la réponse renvoyée à l'utilisateur (`ctx.to_response()` reste
        inchangé). Sert à vérifier le comportement sur une donnée réelle avant
        tout branchement visible — protégé par un try/except pour ne jamais
        faire échouer /strategize si le Design Agent lève une erreur."""
        try:
            stratege_result = ctx.get('stratege')
            if not stratege_result:
                return
            envelope = {"source_agent": "stratege", "content": stratege_result}
            preview = _design_compose(envelope)
            ctx.record_step(
                "[DESIGN AGENT — aperçu] "
                f"format={preview['decision'].get('format_choice')!r} "
                f"recette={preview['decision'].get('recipe_id')!r} "
                f"composants={preview['decision'].get('components_used')!r}"
            )
        except Exception as error:  # noqa: BLE001 — aperçu, ne doit jamais casser /strategize
            ctx.record_step(f"[DESIGN AGENT — aperçu] échec sans conséquence : {error}")
