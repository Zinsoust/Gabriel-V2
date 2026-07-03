from agents.base import BaseAgent


class Architecte(BaseAgent):
    """Agent optionnel — structure des offres, systèmes, parcours ou architectures business."""
    AGENT_ID   = "architecte"
    AGENT_NAME = "L'Architecte"

    def run(self, ctx):
        raise NotImplementedError("L'Architecte n'est pas encore implémenté.")
