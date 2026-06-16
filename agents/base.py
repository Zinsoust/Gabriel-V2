# ─── Contrat de base pour tous les agents Gabriel ────────────────────────────
#
# Chaque agent DOIT hériter de AgentBase.
# Chaque agent DOIT implémenter run(context) → context.
#
# Règle : un agent lit dans context ce dont il a besoin,
#         écrit sa contribution dans context, et retourne context.

class AgentBase:
    AGENT_ID      = ""       # identifiant machine unique
    AGENT_NAME    = ""       # nom affiché
    AGENT_ROLE    = ""       # description courte du rôle
    AGENT_VERSION = "1.0"

    def run(self, context):
        """
        Point d'entrée unique de l'agent.
        Input  : AnalysisContext
        Output : AnalysisContext enrichi
        """
        raise NotImplementedError(f"{self.AGENT_NAME} doit implémenter run(context)")

    def __str__(self):
        return f"{self.AGENT_NAME} v{self.AGENT_VERSION}"

    def __repr__(self):
        return f"<Agent:{self.AGENT_ID} v{self.AGENT_VERSION}>"
