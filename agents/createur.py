# ─── Agent : Le Créateur ─────────────────────────────────────────────────────
#
# Rôle : Générer des contenus marketing directement actionnables.
#
# Responsabilités (Phase 3) :
#   - Hooks (prêts à publier)
#   - Scripts courts (reels, stories)
#   - Posts LinkedIn / Instagram
#   - Angles publicitaires
#   - Titres YouTube
#   - Emails de vente
#   - Messages d'offre
#
# Principe : chaque contenu généré est TRACÉ à une tension ou aspiration réelle.
#            Aucun contenu générique.
#
# Contrat :
#   Input  : AnalysisContext — lit context.get('psychologue') + context.get('stratege')
#   Output : AnalysisContext enrichi — context.contributions['createur'] = rapport

from agents.base import AgentBase


class Createur(AgentBase):

    AGENT_ID      = "createur"
    AGENT_NAME    = "Le Créateur"
    AGENT_ROLE    = "Génère des contenus marketing alignés sur les tensions et aspirations réelles de l'audience."
    AGENT_VERSION = "1.0"

    def run(self, context):
        """
        Génère des contenus directement actionnables à partir de l'analyse.

        TODO Phase 3 — implémenter :
          - hooks[]          (prêts à publier, tracés à une tension)
          - scripts[]        (reels, stories)
          - posts[]          (LinkedIn, Instagram, TikTok)
          - angles_pub[]     (Facebook Ads, YouTube Ads)
          - titres_yt[]      (A/B testables)
          - emails[]         (séquence de vente)
        """
        context.record_step(f"[{self.AGENT_NAME}] — non activé (Phase 3)")

        # Le Créateur lit les tensions, aspirations et recommandations
        # psycho    = context.get('psychologue', {})
        # stratege  = context.get('stratege', {})
        # tensions  = psycho.get('tensions', [])
        # reco      = stratege.get('recommandations_enrichies', {})
        # ...

        # context.add(self.AGENT_ID, rapport_createur)
        return context
