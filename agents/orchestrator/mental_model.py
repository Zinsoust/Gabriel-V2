"""Construction déterministe du modèle mental partagé de l'Orchestrateur.

Cette brique ne décide pas et ne produit pas la réponse finale. Elle transforme
uniquement le contexte vérifié en une représentation compacte du problème.
"""

from dataclasses import asdict, dataclass, field
from typing import Optional


@dataclass
class MentalModel:
    objectif: str = ""
    vision: str = ""
    business_model: str = ""
    probleme: str = ""
    contraintes: list = field(default_factory=list)
    hypotheses: list = field(default_factory=list)
    opportunites: list = field(default_factory=list)
    risques: list = field(default_factory=list)
    analyses_existantes: list = field(default_factory=list)
    donnees_manquantes: list = field(default_factory=list)
    niveau_confiance: float = 0.0
    specialiste_recommande: Optional[str] = None
    question_validation: Optional[str] = None

    def to_dict(self):
        return asdict(self)


def _first(data, *keys):
    for key in keys:
        value = (data or {}).get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _clarification_question(message, profile, intent, has_session_context=False):
    """Retourne au plus une question, seulement si elle change la décision."""
    text = (message or "").strip()
    normalized = text.lower()
    explicit_subjects = (
        "actualité", "tendance", "réglementation", "statistique", "concurrence",
        "marché", "prix", "positionnement", "audience", "contenu", "offre",
        "vente", "croissance", "acquisition", "marketing", "management", "équipe",
    )
    if (intent.get("confidence", 0) >= 0.4 or len(text) >= 90
            or has_session_context
            or any(subject in normalized for subject in explicit_subjects)):
        return None, []

    missing = []
    if not _first(profile, "activite", "activity"):
        missing.append("activité de l'entreprise")
    if not _first(profile, "cible", "current_target", "target"):
        missing.append("public concerné")

    # Une demande courte et sans objet business identifiable ne doit pas être
    # complétée par une supposition. La question porte d'abord sur la décision
    # recherchée : c'est l'information qui réduit le plus l'incertitude.
    if text and not intent.get("agent"):
        return (
            "Pour vous conseiller précisément, quelle décision souhaitez-vous "
            "prendre ou quel résultat business cherchez-vous à obtenir ?",
            missing or ["décision ou résultat attendu"],
        )
    return None, missing


def build_mental_model(message, profile, folder, availability, intent,
                       session_history=None, conversation_memory=None):
    """Construit le modèle mental depuis des données déjà vérifiées côté serveur."""
    profile = profile if isinstance(profile, dict) else {}
    folder = folder if isinstance(folder, dict) else {}
    availability = availability if isinstance(availability, dict) else {}
    conversation_memory = (
        conversation_memory if isinstance(conversation_memory, dict) else {}
    )

    analyses = [name for name in ("psychologue", "stratege", "createur")
                if availability.get(name)]
    session_history = session_history if isinstance(session_history, list) else []
    has_session_context = any(
        isinstance(item, dict) and item.get("role") in ("user", "assistant")
        and str(item.get("content") or "").strip()
        for item in session_history[-4:]
    )
    question, missing = _clarification_question(
        message, profile, intent, has_session_context=has_session_context
    )
    confidence = float(intent.get("confidence") or 0.0)
    if folder:
        confidence = min(1.0, confidence + 0.15)
    if analyses:
        confidence = min(1.0, confidence + 0.1)
    if question:
        confidence = min(confidence, 0.35)

    return MentalModel(
        objectif=(
            _first(folder, "objective")
            or _first(profile, "objectif", "goal")
            or _first(conversation_memory, "workspace_objective")
        ),
        vision=_first(profile, "vision"),
        business_model=_first(profile, "business_model", "modele_economique"),
        probleme=(message or "").strip()[:1200],
        contraintes=[v for v in (
            _first(profile, "contraintes", "constraints"),
            _first(folder, "constraints"),
            " | ".join((conversation_memory.get("facts") or {}).get("contrainte", [])[-2:]),
        ) if v],
        hypotheses=[],
        opportunites=[],
        risques=[],
        analyses_existantes=analyses,
        donnees_manquantes=missing,
        niveau_confiance=round(confidence, 2),
        specialiste_recommande=intent.get("agent"),
        question_validation=question,
    )
