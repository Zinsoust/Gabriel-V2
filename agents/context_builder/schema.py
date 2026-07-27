# ═══════════════════════════════════════════════════════════════════════════
# CONTEXT BUILDER ARCHITECTURE — V1.1 (Conversation structurée)
#
# Ce module est le SCHÉMA — la seule source de vérité sur ce que le Context
# Builder doit collecter. Rien d'autre ne doit redéfinir ces champs ailleurs.
#
# Séparation des responsabilités (voir brief V1.1) :
#   - schema.py         (ce fichier)   → QUOI collecter
#   - store.py                        → OÙ c'est stocké (Supabase)
#   - question_planner.py             → QUELLE question poser ensuite
#   - answer_extractor.py             → COMMENT structurer une réponse libre
#   - tone_renderer.py                → COMMENT le dire (voix de Gabriel)
#   - orchestrator.py                 → CHEF D'ORCHESTRE — pilote les 4 ci-dessus
#
# Le Context Orchestrator ne doit jamais contenir de logique métier propre à
# une seule de ces couches — il les appelle dans l'ordre, il ne les remplace
# pas. C'est la règle explicitement demandée : un seul gros prompt qui fait
# tout à la fois devient instable à mesure que le produit grandit.
# ═══════════════════════════════════════════════════════════════════════════

# ── Les 7 dimensions obligatoires de la V1.1 ─────────────────────────────────
#
# Une dimension = UNE question d'ouverture qui invite une réponse riche en
# langage naturel, dont on extrait ENSUITE plusieurs champs structurés — pas
# une question par champ. C'est ce que montre l'exemple du brief : une seule
# réponse libre ("je travaille seul, je peux mettre 1000€...") produit
# plusieurs champs extraits (team_size, budget_max, budget_preference...).

CONTEXT_DIMENSIONS = [
    {
        "key": "identity",
        "label": "Identité de l'entreprise",
        "opening_question": (
            "Pour commencer simplement : que propose votre entreprise, à qui "
            "s'adresse-t-elle principalement, et sous quelle forme — produit, "
            "service, accompagnement, plateforme ?"
        ),
        "fields": [
            {"key": "offer",   "label": "Ce qui est proposé",       "required": True},
            {"key": "target",  "label": "À qui",                    "required": True},
            {"key": "format",  "label": "Sous quelle forme",        "required": True},
        ],
    },
    {
        "key": "vision",
        "label": "Vision",
        "opening_question": (
            "Que souhaitez-vous réellement construire avec cette entreprise, "
            "et où voulez-vous l'amener ? Il y a aussi des valeurs ou des "
            "limites que vous ne voulez pas sacrifier en chemin — quelles "
            "sont-elles ?"
        ),
        "fields": [
            {"key": "long_term_goal",       "label": "Ce qui est visé à terme",           "required": True},
            {"key": "destination",          "label": "Où l'entreprise doit aller",        "required": True},
            {"key": "client_transformation","label": "Transformation visée pour le client","required": False},
            {"key": "non_negotiables",      "label": "Valeurs / limites non négociables", "required": False},
        ],
    },
    {
        "key": "business_model",
        "label": "Modèle économique",
        "opening_question": (
            "Comment votre entreprise gagne-t-elle de l'argent aujourd'hui ? "
            "Quelles offres sont vendues, à quel prix, et comment un prospect "
            "devient-il client ?"
        ),
        "fields": [
            {"key": "revenue_sources",         "label": "Comment l'argent est gagné",           "required": True},
            {"key": "offers_sold",             "label": "Offres vendues",                       "required": True},
            {"key": "pricing",                 "label": "Prix",                                 "required": True},
            {"key": "conversion_path",         "label": "Comment un prospect devient client",   "required": False},
            {"key": "founder_time_dependency", "label": "Dépendance au temps du dirigeant",     "required": False},
        ],
    },
    {
        "key": "resources",
        "label": "Ressources",
        "opening_question": (
            "Concrètement, sur quelles ressources pouvez-vous vous appuyer "
            "aujourd'hui : budget, équipe, temps disponible, outils, "
            "compétences, audience ou réseau existants ?"
        ),
        "fields": [
            {"key": "budget",   "label": "Budget",              "required": True},
            {"key": "team",     "label": "Équipe",               "required": True},
            {"key": "time",     "label": "Temps disponible",     "required": True},
            {"key": "tools",    "label": "Outils",               "required": False},
            {"key": "skills",   "label": "Compétences",          "required": False},
            {"key": "audience", "label": "Audience existante",   "required": False},
            {"key": "network",  "label": "Réseau",               "required": False},
        ],
    },
    {
        "key": "constraints",
        "label": "Contraintes",
        "opening_question": (
            "Quelles contraintes réelles devons-nous prendre en compte — "
            "financières, humaines, opérationnelles, techniques ou de temps ?"
        ),
        "fields": [
            {"key": "financial",   "label": "Contrainte financière",   "required": True},
            {"key": "human",       "label": "Contrainte humaine",      "required": False},
            {"key": "operational", "label": "Contrainte opérationnelle","required": False},
            {"key": "technical",   "label": "Contrainte technique",    "required": False},
            {"key": "time_constraint", "label": "Contrainte de temps", "required": False},
        ],
    },
    {
        "key": "history",
        "label": "Historique",
        "opening_question": (
            "Qu'avez-vous déjà tenté pour développer cette entreprise, et "
            "qu'est-ce que ça a donné — ce qui a marché, ce qui a échoué, et "
            "pourquoi selon vous ?"
        ),
        "fields": [
            {"key": "actions_tried",    "label": "Actions déjà tentées",  "required": True},
            {"key": "results_observed", "label": "Résultats observés",    "required": False},
            {"key": "failures",         "label": "Échecs",                "required": False},
            {"key": "successes",        "label": "Succès",                "required": False},
            {"key": "assumed_reasons",  "label": "Raisons supposées",     "required": False},
        ],
    },
    {
        "key": "objective",
        "label": "Objectif actuel",
        "opening_question": (
            "Quel est le résultat que vous attendez maintenant, pour quand, "
            "et à quel point c'est prioritaire pour vous ? Comment saurez-vous "
            "que c'est un succès ?"
        ),
        "fields": [
            {"key": "expected_result",     "label": "Résultat attendu",         "required": True},
            {"key": "deadline",            "label": "Délai",                    "required": False},
            {"key": "priority_level",      "label": "Niveau de priorité",       "required": False},
            {"key": "success_indicators",  "label": "Indicateurs de succès",    "required": False},
        ],
    },
]

# ── Vues dérivées, calculées une fois — jamais redéfinies ailleurs ─────────

DIMENSION_BY_KEY = {d["key"]: d for d in CONTEXT_DIMENSIONS}

ALL_FIELD_KEYS = [f["key"] for d in CONTEXT_DIMENSIONS for f in d["fields"]]

FIELD_TO_DIMENSION = {
    f["key"]: d["key"]
    for d in CONTEXT_DIMENSIONS
    for f in d["fields"]
}

FIELD_LABEL_BY_KEY = {
    f["key"]: f["label"]
    for d in CONTEXT_DIMENSIONS
    for f in d["fields"]
}

REQUIRED_FIELD_KEYS = [
    f["key"] for d in CONTEXT_DIMENSIONS for f in d["fields"] if f["required"]
]


def required_fields_for_dimension(dimension_key: str) -> list:
    """Champs obligatoires d'une dimension donnée."""
    dim = DIMENSION_BY_KEY.get(dimension_key)
    if not dim:
        return []
    return [f["key"] for f in dim["fields"] if f["required"]]


def all_fields_for_dimension(dimension_key: str) -> list:
    """Tous les champs (obligatoires + optionnels) d'une dimension donnée."""
    dim = DIMENSION_BY_KEY.get(dimension_key)
    if not dim:
        return []
    return [f["key"] for f in dim["fields"]]


def missing_required_field_labels(dimension_key: str, filled_fields: dict) -> list:
    """Libellés des champs obligatoires encore vides pour UNE dimension.
    Utilisé pour cibler la relance sur ce qui manque réellement, plutôt que
    de reposer toute la question d'ouverture de la dimension (qui redemande
    des points déjà répondus)."""
    dim = DIMENSION_BY_KEY.get(dimension_key)
    if not dim:
        return []
    filled_fields = filled_fields or {}
    return [
        f["label"] for f in dim["fields"]
        if f["required"] and not (filled_fields.get(f["key"]) or "").strip()
    ]


def missing_required_fields(fields: dict) -> list:
    """Champs obligatoires (toutes dimensions confondues) absents ou vides.
    Utilisé par /strategize pour bloquer la génération tant que le contexte
    V1.1 n'est pas suffisant. Liste vide => prêt à générer une stratégie."""
    fields = fields or {}
    missing = []
    for key in REQUIRED_FIELD_KEYS:
        val = fields.get(key, '')
        val = val.strip() if isinstance(val, str) else val
        if not val:
            missing.append({'field': key, 'label': FIELD_LABEL_BY_KEY.get(key, key)})
    return missing


def format_context_for_stratege(fields: dict) -> str:
    """Formate le contexte business V1.1 en texte lisible, groupé par
    dimension, pour l'agent Stratège. Remplace l'ancien formateur à plat
    (schéma legacy à 10 clés) devenu incompatible avec les 33 clés de la V1.1."""
    fields = fields or {}
    lines = []
    for dim in CONTEXT_DIMENSIONS:
        dim_lines = []
        for f in dim["fields"]:
            val = fields.get(f["key"], '')
            val = val.strip() if isinstance(val, str) else ''
            if val:
                dim_lines.append(f"  - {f['label']} : {val}")
        if dim_lines:
            lines.append(f"{dim['label']} :")
            lines.extend(dim_lines)
    return "\n".join(lines)
