"""Contrat des Skills.

Un Skill n'est pas exécutable. C'est un **savoir-faire méthodologique** que
Gabriel injecte dans un raisonnement : une discipline d'écriture, une grille
de lecture, une posture d'analyse. Un Tool *fait* quelque chose ; un Skill
*apprend à un modèle comment* le faire.

Deux propriétés distinguent cette couche d'un simple dictionnaire :

1. **Elle est énumérable.** Un Skill sait dire ce qu'il couvre. Sans cela, un
   planificateur ne peut pas savoir si Gabriel maîtrise « ton notarial » avant
   de promettre à l'utilisateur de l'écrire.

2. **Elle est honnête sur son ignorance.** Le code historique renvoyait une
   chaîne vide pour une tonalité inconnue : indiscernable d'un skill qui n'a
   rien à ajouter. Ici, un fragment déclare toujours s'il vient du catalogue,
   d'un gabarit de repli, ou de rien du tout.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Callable, Mapping, Optional


class SkillError(Exception):
    """Erreur de la couche Skill."""


@dataclass(frozen=True)
class SkillFragment:
    """Ce qu'un Skill produit : du texte à injecter, et sa provenance."""

    skill_id: str
    key: str            # la clé canonique retenue (après alias)
    requested: str      # ce qui a été demandé, avant normalisation
    content: str
    origin: str         # 'catalog' | 'fallback' | 'none'

    @property
    def known(self) -> bool:
        """Le savoir-faire demandé figure-t-il réellement au catalogue ?"""
        return self.origin == 'catalog'

    @property
    def empty(self) -> bool:
        return not self.content.strip()

    def __str__(self) -> str:
        return self.content


@dataclass(frozen=True)
class SkillSpec:
    """Fiche d'identité d'un Skill, lisible par le Core."""

    id: str
    name: str
    description: str
    domain: str
    source: str = ''            # d'où vient la méthodologie (traçabilité)
    injectable: bool = True     # destiné à entrer dans un prompt
    accepts_free_text: bool = False  # gère-t-il une demande hors catalogue ?

    def describe(self) -> dict:
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'domain': self.domain,
            'source': self.source,
            'injectable': self.injectable,
            'accepts_free_text': self.accepts_free_text,
        }


class Skill(ABC):
    """Un savoir-faire consultable."""

    spec: SkillSpec

    @abstractmethod
    def keys(self) -> tuple:
        """Les variantes que ce skill couvre réellement."""

    @abstractmethod
    def normalize(self, requested: str) -> str:
        """Ramène une demande vers une clé canonique (alias, casse, accents)."""

    @abstractmethod
    def render(self, requested: str) -> SkillFragment:
        """Produit le fragment à injecter pour la demande donnée."""

    def covers(self, requested: str) -> bool:
        """Gabriel maîtrise-t-il vraiment cette variante ?"""
        return self.normalize(requested) in self.keys()

    def describe(self) -> dict:
        d = self.spec.describe()
        d['keys'] = list(self.keys())
        return d


@dataclass
class CatalogSkill(Skill):
    """Skill adossé à un catalogue de fragments déjà rédigés.

    C'est la forme des savoir-faire déjà énumérables dans Gabriel : un
    dictionnaire clé → bloc de méthode, plus une table d'alias. Le catalogue
    n'est pas recopié : on l'enveloppe tel quel, pour que le Skill et le code
    historique ne puissent jamais diverger.
    """

    spec: SkillSpec
    catalog: Mapping[str, str]
    aliases: Mapping[str, str] = field(default_factory=dict)
    normalizer: Optional[Callable[[str], str]] = None
    fallback: Optional[Callable[[str], str]] = None

    def keys(self) -> tuple:
        return tuple(sorted(self.catalog))

    def normalize(self, requested: str) -> str:
        raw = (requested or '').strip()
        if not raw:
            return ''
        if self.normalizer is not None:
            return self.normalizer(raw)
        return self.aliases.get(raw.lower(), raw.lower())

    def render(self, requested: str) -> SkillFragment:
        key = self.normalize(requested)
        if key in self.catalog:
            return SkillFragment(self.spec.id, key, requested or '',
                                 self.catalog[key], 'catalog')
        if key and self.fallback is not None:
            return SkillFragment(self.spec.id, key, requested or '',
                                 self.fallback(requested), 'fallback')
        return SkillFragment(self.spec.id, key, requested or '', '', 'none')
