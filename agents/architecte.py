# ─── Agent : L'Architecte ────────────────────────────────────────────────────
#
# Rôle : Transformer l'analyse en plan d'action concret et séquencé.
#
# Responsabilités (Phase 2) :
#   - Plan d'action 7j / 30j / 90j
#   - Priorisation des actions par impact
#   - Séquençage logique (quick wins → moyen terme → vision)
#   - Identification des actions à ne PAS faire (anti-actions)
#
# Contrat :
#   Input  : AnalysisContext — lit context.get('psychologue') + context.get('stratege')
#   Output : AnalysisContext enrichi — context.contributions['architecte'] = rapport

from agents.base import AgentBase


class Architecte(AgentBase):

    AGENT_ID      = "architecte"
    AGENT_NAME    = "L'Architecte"
    AGENT_ROLE    = "Structure l'analyse en plan d'action séquencé — 7 jours, 30 jours, 90 jours."
    AGENT_VERSION = "1.0"

    def run(self, context):
        """
        Produit le plan d'action final à partir de l'ensemble de l'analyse.

        TODO Phase 2 — implémenter :
          - plan_action {
              7_jours:  [actions immédiates],
              30_jours: [actions court terme],
              90_jours: [actions moyen terme],
            }
          - priorites []    (classées par score d'impact)
          - anti_actions [] (ce qu'il ne faut PAS faire)
        """
        context.record_step(f"[{self.AGENT_NAME}] — non activé (Phase 2)")

        # L'Architecte synthétise tout ce que les agents précédents ont produit
        # psycho   = context.get('psychologue', {})
        # stratege = context.get('stratege', {})
        # ...

        # context.add(self.AGENT_ID, rapport_architecte)
        return context
