"""Design Agent — moteur interne de restitution des livrables de Gabriel.

Ne modifie jamais le code source : c'est le mode DESIGN_RUNTIME, le seul
implémenté ici. Il reçoit un résultat métier déjà produit par un autre agent
(Psychologue, Stratège, Créateur, Cross-Analyse…), en observe la forme réelle
via l'outil `design.describe_content_shape`, et choisit comment le composer à
partir des composants Gabriel déjà approuvés (DESIGN.md, §5) — jamais un
format inventé, jamais un composant qui n'existe pas encore dans le Design
System.

Le mode DESIGN_DEVELOPMENT (patch de composants, évolution du Design System)
n'est pas implémenté ici : cet agent ne touche jamais au dépôt, conformément à
la contrainte de sécurité posée par l'utilisateur — un Design Agent runtime ne
doit jamais pouvoir réécrire le code de production suite à une requête.

Décision de latence (voir conversation) : pas de critique en direct par
requête. `compose()`, le chemin réellement emprunté à chaque affichage, ne
fait AUCUN appel LLM — il reconnaît une recette déjà validée
(`agents/design_recipes.py`) et l'instancie. Si rien ne correspond, il
dégrade vers un conteneur générique déjà approuvé et journalise le manque.
`draft_recipe_with_llm()` reste disponible mais n'est jamais appelé au
runtime : c'est l'outil hors ligne qui sert à *fabriquer* une nouvelle
recette à valider, pas à improviser un affichage devant l'utilisateur.
"""

from __future__ import annotations

import json
from typing import Any

from agents import design_recipes
from agents.base import BaseAgent
from core import llm_client as _llm
from core.ai_json import parse_ai_json
from skills import registry as skill_registry
from tools import registry as tool_registry


# Composants Gabriel réellement livrés (DESIGN.md, §5, templates/stratege.html
# et templates/psychologue.html). Le Design Agent ne peut choisir que parmi
# cette liste — jamais un composant qu'il invente, même cohérent avec la
# méthodologie. Un besoin non couvert est un signal pour l'équipe de
# développement (mode DESIGN_DEVELOPMENT), pas quelque chose à combler ici.
APPROVED_COMPONENTS = (
    {"name": "confidence_gauge",
     "usage": "Un ou deux scores de confiance/alignement comparables (0-1)."},
    {"name": "priority_list",
     "usage": "Liste d'éléments avec titre/signal/impact/délai, sans cadre."},
    {"name": "status_pill",
     "usage": "Statut binaire réellement connu (à surveiller / fait)."},
    {"name": "price_position_scale",
     "usage": "Positionnement prix parmi 4 étapes fixes exactes."},
    {"name": "editorial_numbered_list",
     "usage": "Plan en phases numérotées, toutes à égalité."},
    {"name": "selection_chip",
     "usage": "Ensemble d'éléments sélectionnables/sélectionnés."},
    {"name": "full_gradient_badge_card",
     "usage": "Un seul moment de confiance/validation par écran, jamais plusieurs."},
    {"name": "premium_card_frame",
     "usage": "Cadre générique pour une carte de décision isolée."},
)


_SYSTEM = """Tu es le Design Agent de Gabriel, en mode DESIGN_RUNTIME.

Tu ne modifies jamais de code. Tu reçois un résultat métier déjà produit, sa
forme déterministe, et la liste exacte des composants Gabriel déjà approuvés.
Tu dois choisir comment le restituer, en composant UNIQUEMENT à partir de ces
composants. Si aucun composant approuvé ne convient à une partie du contenu,
dis-le explicitement plutôt que d'inventer un composant — un manque de
composant est un signal pour l'équipe de développement (mode
DESIGN_DEVELOPMENT), pas un problème que tu résous toi-même.

Réponds en JSON strict, avec exactement ces clés :
{
  "format_choice": "nom du format retenu, en français, court",
  "components_used": ["noms exacts des composants approuvés utilisés, [] si aucun ne convient"],
  "field_mapping": {"champ_du_contenu": "prop du composant, ou description si texte libre"},
  "missing_components": ["besoin non couvert par le catalogue actuel, [] si aucun"],
  "justification": "1-2 phrases : pourquoi ce choix découle de la forme du contenu, pas du goût"
}"""


def compose(envelope: dict[str, Any]) -> dict[str, Any]:
    """Restitue un résultat métier — chemin runtime réel, sans appel LLM.

    ``envelope`` : ``{"source_agent": str, "content": dict}``. N'écrit jamais
    sur le dépôt — c'est tout le contrat DESIGN_RUNTIME. Reconnaît une recette
    déjà validée (rapide, déterministe) ; si aucune ne correspond, dégrade
    vers un conteneur générique déjà approuvé et journalise le manque pour le
    mode DESIGN_DEVELOPMENT — jamais d'improvisation en direct.
    """
    shape = tool_registry.get("design.describe_content_shape").run(envelope=envelope)

    decision = design_recipes.match_recipe(shape, envelope)
    if decision is None:
        design_recipes.log_gap(shape, envelope)
        decision = {
            "format_choice": "bloc générique (aucune recette validée pour cette forme)",
            "components_used": [design_recipes.FALLBACK_COMPONENT],
            "field_mapping": {},
            "missing_components": ["recette à valider pour cette forme de contenu"],
            "justification": (
                "Aucune recette validée ne correspond à cette forme — repli "
                "sur un conteneur générique plutôt qu'un affichage inventé. "
                "Manque journalisé pour le mode DESIGN_DEVELOPMENT."),
            "recipe_id": None,
        }

    return {"shape": shape, "decision": decision}


def draft_recipe_with_llm(envelope: dict[str, Any]) -> dict[str, Any]:
    """Outil hors ligne (mode DESIGN_DEVELOPMENT) : propose une recette pour
    une forme non couverte, à valider par un humain avant tout ajout à
    `agents/design_recipes.py`. N'est jamais appelé depuis `compose()` — un
    appel LLM par requête est exactement ce que la décision de latence écarte.
    """
    shape = tool_registry.get("design.describe_content_shape").run(envelope=envelope)
    methodology = skill_registry.render(
        "design.presentation_composition", requested="design"
    ).content

    prompt = json.dumps(
        {
            "methodologie": methodology,
            "resultat_metier": envelope,
            "forme_detectee": shape,
            "composants_approuves": APPROVED_COMPONENTS,
        },
        ensure_ascii=False,
    )

    response = _llm.complete(
        prompt,
        system=_SYSTEM,
        tier="deep",
        max_tokens=1200,
        timeout_ms=120_000,
        label="design_agent.draft_recipe_with_llm",
        throttled=False,
    )
    decision = parse_ai_json(response.text, on_error="raise", label="design_agent")
    return {"shape": shape, "decision": decision}


class DesignAgent(BaseAgent):
    """Point d'entrée agent — jamais sélectionnable par l'utilisateur.

    Pas de ``direct_access`` (cf. `AgentSpec` 'design' dans
    `agents/catalog.py`) : appelé uniquement en interne, après qu'un autre
    agent a produit un résultat métier, jamais depuis l'UI.
    """

    AGENT_ID = "design"
    AGENT_NAME = "Design Agent"

    def run(self, ctx: dict[str, Any]) -> dict[str, Any]:
        envelope = ctx.get("envelope") if isinstance(ctx, dict) else None
        if not envelope:
            raise ValueError(
                "DesignAgent.run attend ctx['envelope'] = "
                "{'source_agent': str, 'content': dict}"
            )
        return compose(envelope)
