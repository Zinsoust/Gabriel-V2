"""Synthèse — réunir les contributions des agents sans en perdre.

Dernière étape du schéma d'architecture, la seule qui manquait encore :

    Demande → Planner → Exécution → Critic → **Synthèse** → Réponse

Ce que faisait déjà `AnalysisContext.to_response()` : fusionner à plat les
dictionnaires produits par chaque agent. Ce qu'il ne faisait pas : dire ce
que cette fusion écrase. `result.update(data)` écrase silencieusement toute
clé déjà présente — la contribution d'un agent peut disparaître sans erreur,
sans avertissement, sans trace.

Le piège est aujourd'hui **latent** : le schéma de sortie du Stratège ne
recoupe pas celui du Psychologue. Mais rien ne le garantit — ces clés
viennent de réponses de modèle, pas d'un contrat vérifié. Une clé
inattendue suffit à faire disparaître un rapport entier.

Ce module ne change pas la fusion : il l'observe. `to_response()` garde
exactement le même résultat — du code de production en dépend — et la
synthèse ajoute à côté la provenance de chaque clé et la liste de ce qui a
été écrasé. Corriger la fusion serait un changement de comportement ;
rendre visible ce qu'elle perd ne l'est pas.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Tuple


@dataclass(frozen=True)
class Collision:
    """Une clé produite par plusieurs agents — une seule survit."""

    key: str
    kept_from: str            # l'agent dont la valeur figure dans la réponse
    overwritten_from: Tuple[str, ...]   # ceux dont la valeur a disparu

    def describe(self) -> dict:
        return {
            'key': self.key,
            'kept_from': self.kept_from,
            'overwritten_from': list(self.overwritten_from),
        }


@dataclass(frozen=True)
class Synthesis:
    """La réponse réunie, et la vérité sur la façon dont elle a été réunie."""

    response: Dict[str, Any]
    provenance: Dict[str, str] = field(default_factory=dict)  # clé → agent retenu
    collisions: Tuple[Collision, ...] = ()
    contributors: Tuple[str, ...] = ()

    @property
    def lossless(self) -> bool:
        """Aucune contribution n'a été écrasée."""
        return not self.collisions

    def describe(self) -> dict:
        return {
            'contributors': list(self.contributors),
            'keys': len(self.response),
            'lossless': self.lossless,
            'collisions': [c.describe() for c in self.collisions],
        }

    def explain(self) -> str:
        """En clair, pour un journal d'exécution ou un compte rendu."""
        qui = ', '.join(self.contributors) or 'aucun agent'
        lignes = [f"Synthèse de {qui} — {len(self.response)} clés"]
        if self.lossless:
            lignes.append("  aucune contribution perdue")
        else:
            for c in self.collisions:
                perdus = ', '.join(c.overwritten_from)
                lignes.append(
                    f"  ⚠ « {c.key} » : valeur de {c.kept_from} retenue, "
                    f"celle de {perdus} écrasée")
        return '\n'.join(lignes)


def synthesize(ctx) -> Synthesis:
    """Réunit les contributions d'un contexte d'analyse.

    Le résultat est identique à `ctx.to_response()` — même ordre de fusion,
    même valeurs. Ce qui s'y ajoute est la lecture de ce qui s'est passé.
    """
    response: Dict[str, Any] = {}
    provenance: Dict[str, str] = {}
    ecrases: Dict[str, List[str]] = {}
    contributors: List[str] = []

    # Même parcours que `to_response` : l'ordre d'insertion des résultats
    # décide qui l'emporte. Le reproduire, plutôt que de le corriger, garantit
    # que la synthèse décrit la réponse réellement rendue.
    for agent_id, data in ctx._results.items():
        if not isinstance(data, dict):
            continue
        contributors.append(agent_id)
        for key, value in data.items():
            if key in provenance:
                ecrases.setdefault(key, []).append(provenance[key])
            response[key] = value
            provenance[key] = agent_id

    collisions = tuple(
        Collision(key=key, kept_from=provenance[key],
                  overwritten_from=tuple(perdants))
        for key, perdants in sorted(ecrases.items())
    )
    return Synthesis(response=response, provenance=provenance,
                     collisions=collisions, contributors=tuple(contributors))
