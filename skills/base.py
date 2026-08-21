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

    # Les sept questions qu'un planificateur doit pouvoir poser à un Skill
    # avant de le mobiliser — pas des champs décoratifs : chacun répond à une
    # décision réelle (le convoquer ou non, avec quoi, et jusqu'où lui faire
    # confiance). Par défaut vides plutôt qu'obligatoires, pour ne pas casser
    # un Skill déjà déclaré avant que sa fiche soit complétée — mais un Skill
    # incomplet doit rester visible comme tel, pas silencieusement accepté.
    solves: str = ''                        # ce qu'il sait résoudre
    when_to_use: str = ''                    # quand le convoquer
    required_info: tuple[str, ...] = ()      # ce qu'il faut lui fournir
    methodology_summary: str = ''            # sa méthode, en une ou deux phrases
    allowed_tools: tuple[str, ...] = ()      # Tools qu'il peut mobiliser
    limitations: str = ''                    # ce qu'il ne couvre pas
    output_format: str = ''                  # forme de ce qu'il produit

    def describe(self) -> dict:
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'domain': self.domain,
            'source': self.source,
            'injectable': self.injectable,
            'accepts_free_text': self.accepts_free_text,
            'solves': self.solves,
            'when_to_use': self.when_to_use,
            'required_info': list(self.required_info),
            'methodology_summary': self.methodology_summary,
            'allowed_tools': list(self.allowed_tools),
            'limitations': self.limitations,
            'output_format': self.output_format,
        }

    def is_fully_documented(self) -> bool:
        """Les six champs textuels sont-ils réellement renseignés ?

        Un Skill enregistré sans cette fiche complète reste utilisable — on ne
        bloque personne — mais un planificateur qui choisit entre plusieurs
        Skills doit pouvoir écarter ceux qu'il ne peut pas encore évaluer.

        `required_info` est délibérément exclu de ce test : un tuple vide y
        est une réponse légitime (« ce Skill ne demande aucune information »,
        vrai pour la grille psychologique) et non une case oubliée —
        contrairement aux six champs textuels, qui n'ont pas de valeur vide
        honnête.
        """
        return all((self.solves, self.when_to_use, self.methodology_summary,
                   self.limitations, self.output_format))


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
    # Clé substituée silencieusement sur une demande non reconnue — comportement
    # historique du Créateur : un format inconnu se rabat sur 'hooks' plutôt que
    # d'échouer. Distinct de `fallback` : ici on sert une entrée existante du
    # catalogue, pas un texte généré pour l'occasion.
    default_key: Optional[str] = None

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
        if self.default_key is not None and self.default_key in self.catalog:
            # Servi, mais ce n'est pas ce qui a été demandé : `known` doit
            # rester faux, sinon un format mal orthographié passerait pour
            # reconnu.
            return SkillFragment(self.spec.id, self.default_key, requested or '',
                                 self.catalog[self.default_key], 'default')
        return SkillFragment(self.spec.id, key, requested or '', '', 'none')


@dataclass
class CorpusSkill(Skill):
    """Skill adossé à un corpus documentaire récupéré par pertinence.

    Troisième forme de Skill, née d'un besoin que ``CatalogSkill`` ne sait pas
    exprimer : le corpus stratégique de Gabriel contient 39 méthodes nommées
    (formules de pricing, design d'offre, schémas de marché), mais on n'en
    choisit jamais une *par son nom* — on décrit une situation et le corpus
    rend les méthodes pertinentes. Forcer ce corpus dans un catalogue à clés
    mentirait sur la façon dont il est réellement consulté.

    Ce que cette forme apporte, et que la recherche documentaire seule ne
    donne pas : **l'énumérabilité**. Aujourd'hui, personne ne peut demander
    « quelles méthodes de pricing Gabriel connaît-il ? » — le corpus n'est
    atteignable qu'à travers une requête sémantique, donc invisible tant
    qu'on n'a pas deviné les bons mots. ``keys()`` répond à cette question.

    ``retrieve`` reçoit la requête et rend le texte à injecter ; il n'est pas
    implémenté ici, parce que la récupération est le travail d'un Tool
    (``knowledge.search``), pas d'un Skill — un Skill enseigne, il n'exécute
    pas.
    """

    spec: SkillSpec
    entries: Mapping[str, str]              # id → libellé lisible de la méthode
    retrieve: Callable[[str], str]          # requête → texte à injecter

    def keys(self) -> tuple:
        return tuple(sorted(self.entries))

    def normalize(self, requested: str) -> str:
        """Un identifiant de méthode, si la demande en cite un ; sinon vide.

        Contrairement à un catalogue, une requête libre n'a pas vocation à
        « tomber » sur une clé : c'est le mode normal d'usage, pas un échec.
        """
        raw = (requested or '').strip().lower()
        return raw if raw in self.entries else ''

    def render(self, requested: str) -> SkillFragment:
        query = (requested or '').strip()
        if not query:
            return SkillFragment(self.spec.id, '', '', '', 'none')
        content = self.retrieve(query)
        if not content:
            # Corpus indisponible ou aucune méthode pertinente : le dire plutôt
            # que de rendre un fragment vide indiscernable d'un skill muet.
            return SkillFragment(self.spec.id, '', requested, '', 'none')
        return SkillFragment(self.spec.id, self.normalize(requested), requested,
                             content, 'corpus')

    def describe(self) -> dict:
        d = super().describe()
        d['entries'] = dict(self.entries)
        return d
