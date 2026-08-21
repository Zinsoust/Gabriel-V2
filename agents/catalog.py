"""Déclaration des agents Gabriel.

Les fiches décrivent les agents tels qu'ils sont, pas tels qu'on aimerait
qu'ils soient. En particulier : `Createur` n'a jamais eu de `run()` utilisable
et `Architecte` n'est pas implémenté — ces deux faits sont déclarés plutôt que
masqués derrière une interface uniforme.

Le statut n'est pas écrit en dur : il est *constaté* au chargement. Un agent
dont l'import échoue passe en `unavailable` au lieu d'être annoncé disponible.
"""

from agents.registry import (STATUS_AVAILABLE, STATUS_PLANNED,
                             STATUS_UNAVAILABLE, AgentRegistry, AgentSpec)
from skills import registry as skill_registry
from tools import registry as tool_registry

registry = AgentRegistry(tool_registry=tool_registry, skill_registry=skill_registry)


def _loader(module_path: str, class_name: str):
    """Charge la classe à la demande — un agent en panne n'empêche pas les
    autres de fonctionner, comportement déjà en place dans agents/__init__."""
    def load():
        import importlib
        return getattr(importlib.import_module(module_path), class_name)
    return load


def _observed_status(module_path: str, class_name: str, expected: str) -> str:
    """Constate si l'agent se charge réellement."""
    if expected != STATUS_AVAILABLE:
        return expected
    try:
        _loader(module_path, class_name)()
        return STATUS_AVAILABLE
    except Exception as error:   # noqa: BLE001 — on veut tout attraper ici
        print(f"[GABRIEL] Agent « {class_name} » indisponible : {error}")
        return STATUS_UNAVAILABLE


_DECLARATIONS = (
    (
        AgentSpec(
            id='psychologue',
            name='Le Psychologue',
            description=(
                "Analyse la psychologie réelle d'une audience à partir de ses "
                "commentaires : émotions, postures, objections, personas."),
            entrypoint='run',
            consumes=('comments',),
            produces='psychologue',
            tools=('audience.score_comments', 'audience.compute_kpis',
                   'audience.compute_dashboard'),
            skills=('psychology.human_understanding_grid',),
            route='/psychologue',
        ),
        'agents.psychologue', 'Psychologue', STATUS_AVAILABLE,
    ),
    (
        AgentSpec(
            id='stratege',
            name='Le Stratège',
            description=(
                "Transforme la psychologie d'une audience en décision "
                "marketing immédiate : offre, format, action, mesure."),
            entrypoint='run',
            # Dépendance réelle : `run` lit ctx.get('psychologue'). Un plan qui
            # l'ignorerait produirait une stratégie sans matière.
            consumes=('psychologue',),
            # Souple : app.py lance aussi le Stratège sur un brief texte seul.
            optional_consumes=('psychologue',),
            produces='stratege',
            tools=('adaptation.psycho_to_strategy_context',),
            skills=('strategy.decision_reasoning', 'strategy.business_corpus'),
            route='/stratege',
        ),
        'agents.stratege', 'Stratege', STATUS_AVAILABLE,
    ),
    (
        AgentSpec(
            id='createur',
            name='Le Créateur',
            description=(
                "Rédige textes et scripts marketing selon une discipline de "
                "tonalité et une émotion cible."),
            # `run()` lève : le vrai point d'entrée a toujours été celui-ci.
            entrypoint='generate_script_or_text',
            consumes=('psychologue', 'stratege'),
            # Souples également : `_resolve_psycho` peut ne rien rendre, et la
            # stratégie est facultative dans la requête de génération.
            optional_consumes=('psychologue', 'stratege'),
            produces='createur',
            skills=('writing.tone_discipline', 'writing.emotion_directive',
                   'writing.content_structure'),
            route='/createur',
        ),
        'agents.createur', 'Createur', STATUS_AVAILABLE,
    ),
    (
        AgentSpec(
            id='architecte',
            name="L'Architecte",
            description=(
                "Structure des offres, systèmes, parcours ou architectures "
                "business. Prévu, pas encore implémenté."),
            status=STATUS_PLANNED,
            direct_access=False,
        ),
        'agents.architecte', 'Architecte', STATUS_PLANNED,
    ),
)


def register_all() -> AgentRegistry:
    from dataclasses import replace
    for spec, module_path, class_name, expected in _DECLARATIONS:
        status = _observed_status(module_path, class_name, expected)
        loader = _loader(module_path, class_name) if status != STATUS_PLANNED else None
        registry.register(replace(spec, status=status), loader=loader)
    return registry


register_all()
