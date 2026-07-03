# ─── Gabriel — Orchestrateur multi-agents ────────────────────────────────────
#
# Deux pipelines indépendants :
#   run_psycho()   → Psychologue uniquement (commentaires → insights humains)
#   run_stratege() → Stratège uniquement   (insights + profil projet → décision)
#
# Chaque agent reçoit l'AnalysisContext, lit les contributions précédentes,
# dépose la sienne, retourne le contexte enrichi.

from agents.context     import AnalysisContext
from agents.psychologue import Psychologue
from agents.stratege    import Stratege
from agents.createur    import Createur


class Gabriel:

    def __init__(self):
        self.psychologue = Psychologue()
        self.stratege    = Stratege()
        self.createur    = Createur()

    # ── Pipeline 1 : Analyse Psychologique ───────────────────────────────────

    def run_psycho(self, comments, video_context="", title=""):
        """
        Analyse les commentaires et retourne les insights psychologiques.
        N'a pas besoin du profil projet — s'appuie uniquement sur les données audience.
        """
        ctx = AnalysisContext(
            comments=comments,
            brain_context="",
            video_context=video_context,
            title=title,
        )
        ctx.record_step(f"[GABRIEL] Pipeline psychologique — {len(comments)} commentaires")

        try:
            ctx = self.psychologue.run(ctx)
        except Exception as e:
            ctx.record_error(self.psychologue.AGENT_ID, str(e))
            raise RuntimeError(f"[{self.psychologue.AGENT_NAME}] Erreur critique : {e}") from e

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

        try:
            ctx = self.stratege.run(ctx)
        except Exception as e:
            ctx.record_error(self.stratege.AGENT_ID, str(e))
            raise RuntimeError(f"[{self.stratege.AGENT_NAME}] Erreur critique : {e}") from e

        ctx.record_step("[GABRIEL] Pipeline stratégique terminé")
        return ctx.to_response()

    # ── Pipeline 3 : Création de Contenu ─────────────────────────────────────

    def run_createur(self, content_type, psycho_data, strategie_data, params=None):
        """
        Génère du contenu créatif basé sur les insights psychologiques et la stratégie.
        content_type : 'hooks' | 'script' | 'email' | 'post' | 'angles'
        """
        return self.createur.create_content(content_type, psycho_data, strategie_data, params)
