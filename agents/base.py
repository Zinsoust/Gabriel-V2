class BaseAgent:
    AGENT_ID   = "base"
    AGENT_NAME = "Base"

    def run(self, ctx):
        raise NotImplementedError

AgentBase = BaseAgent  # alias — compatibilité agents/__init__.py
