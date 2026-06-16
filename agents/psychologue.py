# ─── Agent : Le Psychologue ───────────────────────────────────────────────────
#
# Rôle : Comprendre l'âme derrière les mots.
# Il ne lit pas des commentaires — il lit des signaux humains.
#
# Responsabilités :
#   - Labellisation rapide par commentaire (émotion, intention, signal)
#   - Sélection des commentaires à forte valeur
#   - Analyse psychologique profonde (tensions, aspirations, A→B)
#   - Génération des personas
#   - Brief exécutif
#
# Contrat :
#   Input  : AnalysisContext (lit context.comments, brain_context, video_context, title)
#   Output : AnalysisContext enrichi — context.contributions['psychologue'] = rapport

from agents.base import AgentBase
from analyzer import analyze_comments


class Psychologue(AgentBase):

    AGENT_ID      = "psychologue"
    AGENT_NAME    = "Le Psychologue"
    AGENT_ROLE    = "Comprend l'âme derrière les mots — émotions, tensions, aspirations, transformation A→B."
    AGENT_VERSION = "1.0"

    def run(self, context):
        """
        Analyse psychologique complète des commentaires.
        Lit les données brutes dans context.input.
        Dépose le rapport dans context.contributions['psychologue'].
        """
        context.record_step(f"[{self.AGENT_NAME}] Démarrage — {len(context.comments)} commentaires")

        rapport = analyze_comments(
            context.comments,
            brain_context=context.brain_context,
            video_context=context.video_context,
            title=context.title,
        )

        context.add(self.AGENT_ID, rapport)
        context.record_step(f"[{self.AGENT_NAME}] Rapport déposé")
        return context
