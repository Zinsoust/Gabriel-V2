from agents.base import BaseAgent


class Psychologue(BaseAgent):
    AGENT_ID   = "psychologue"
    AGENT_NAME = "Le Psychologue"

    def run(self, ctx):
        from core.analyzer import analyze_comments
        result = analyze_comments(
            ctx.comments,
            ctx.brain_context,
            ctx.video_context,
            ctx.title,
        )
        ctx.add(self.AGENT_ID, result)
        return ctx
