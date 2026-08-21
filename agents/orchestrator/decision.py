"""Decision Engine pur : il choisit une aide, il ne rédige jamais la réponse."""

from dataclasses import asdict, dataclass
import unicodedata
from typing import Optional


@dataclass(frozen=True)
class OrchestratorDecision:
    action: str
    use_web: bool
    use_existing_analysis: bool
    specialist: Optional[str]
    rationale: str

    def to_dict(self):
        return asdict(self)


_CURRENT_SIGNALS = (
    "actualite", "aujourd'hui", "recent", "tendance", "reglementation",
    "loi", "statistique", "chiffre", "marche actuel", "concurrence actuelle",
    "benchmark actuel", "prix actuel", "en 2026", "cherche sur internet",
    "recherche internet", "recherche web", "sur internet", "sur le web",
    "google", "concurrent direct", "concurrents directs",
)


def _norm(text):
    value = unicodedata.normalize("NFD", (text or "").lower())
    return "".join(c for c in value if unicodedata.category(c) != "Mn")


def decide_help(message, intent, mental_model):
    question = mental_model.get("question_validation")
    if question:
        return OrchestratorDecision(
            action="clarify", use_web=False, use_existing_analysis=False,
            specialist=None, rationale="Le contexte ne permet pas encore une recommandation fiable.",
        )

    normalized = _norm(message)
    use_web = any(signal in normalized for signal in _CURRENT_SIGNALS)
    use_existing = intent.get("kind") == "transversal" and bool(
        mental_model.get("analyses_existantes")
    )
    specialist = intent.get("agent")
    if specialist:
        action = "recommend_specialist"
        rationale = "Une expertise spécialisée créerait davantage de valeur."
    elif use_web:
        action = "research_then_answer"
        rationale = "La décision dépend d'informations actuelles vérifiables."
    elif use_existing:
        action = "synthesize_existing"
        rationale = "Les analyses existantes doivent être reliées avant de conclure."
    else:
        action = "answer_directly"
        rationale = "Le contexte disponible permet une première réponse utile."
    return OrchestratorDecision(action, use_web, use_existing, specialist, rationale)
