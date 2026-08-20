"""Registre des mémoires de Gabriel.

Cinq types de mémoire existent déjà dans le produit — conversation,
utilisateur, business, audience, stratégique — mais rien ne les déclare
ensemble. Chacun vit dans son propre mécanisme de stockage, avec son propre
contrat d'accès, sans qu'aucun endroit ne réponde à la question « quelle
mémoire Gabriel a-t-il sur ce sujet, et d'où vient-elle ? ».

Comme pour les Tools et les Skills, ce module ne réécrit aucun mécanisme de
stockage : il référence les fonctions d'accès qui existent déjà et leur donne
une fiche commune — nom, ce qu'il faut fournir pour lire, la provenance de ce
qui revient.

Une limite honnête, découverte en construisant ce registre : trois des cinq
mémoires (utilisateur, business, audience) vivent aujourd'hui dans
``app.py``, qui n'est importé par aucun autre module du projet — c'est la
feuille de l'arbre d'imports, jamais une racine. Les y importer depuis ce
module créerait une dépendance qui n'existe nulle part ailleurs dans le code,
et ferait courir tout l'effet de bord du chargement de ``app.py`` (création de
l'app Flask, clients externes) au moment où quelqu'un consulterait juste le
registre. Ces trois mémoires sont donc déclarées ``STATUS_PLANNED`` — visibles
dans le catalogue, mais pas encore lisibles par lui — jusqu'à ce que leurs
fonctions d'accès soient déplacées hors de ``app.py``, comme cela a déjà été
fait pour les outils du Psychologue et les savoir-faire du Créateur.
"""

from dataclasses import dataclass, field
from typing import Callable, Dict, Optional, Tuple

STATUS_AVAILABLE = 'available'
STATUS_PLANNED = 'planned'
_STATUSES = (STATUS_AVAILABLE, STATUS_PLANNED)


class MemoryError(Exception):
    """Erreur de la couche Memory."""


class MemoryNotFound(MemoryError, KeyError):
    """Aucune mémoire déclarée sous cet identifiant."""


class MemoryUnavailable(MemoryError):
    """La mémoire est déclarée mais son accès n'est pas encore branché."""


@dataclass(frozen=True)
class MemorySpec:
    """Fiche d'identité d'une mémoire, lisible par le Core."""

    id: str
    name: str
    description: str
    scope: str                       # 'conversation' | 'user' | 'session' | 'global'
    required_keys: Tuple[str, ...] = ()   # ce qu'il faut fournir pour lire
    status: str = STATUS_AVAILABLE
    source: str = ''                 # où vit réellement le mécanisme de stockage

    def __post_init__(self):
        if self.status not in _STATUSES:
            raise ValueError(
                f"Statut invalide pour « {self.id} » : {self.status!r}. "
                f"Attendu : {', '.join(_STATUSES)}.")

    @property
    def usable(self) -> bool:
        return self.status == STATUS_AVAILABLE

    def describe(self) -> dict:
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'scope': self.scope,
            'required_keys': list(self.required_keys),
            'status': self.status,
            'usable': self.usable,
            'source': self.source,
        }


@dataclass(frozen=True)
class MemoryEntry:
    """Ce qu'une lecture de mémoire renvoie : du contenu, et sa provenance.

    La provenance existe parce qu'elle est déjà calculée en silence par le
    code d'origine sans jamais être rendue à l'appelant — en particulier le
    contexte business, qui retombe en cascade sur trois sources différentes
    (requête, entretien stratégique, profil hérité) sans jamais dire
    laquelle a répondu.
    """

    spec_id: str
    content: object
    empty: bool
    provenance: str = ''

    def describe(self) -> dict:
        return {
            'spec_id': self.spec_id,
            'empty': self.empty,
            'provenance': self.provenance,
        }


class RegisteredMemory:
    def __init__(self, spec: MemorySpec, fetch: Optional[Callable] = None):
        self.spec = spec
        self._fetch = fetch

    def fetch(self, **kwargs) -> MemoryEntry:
        if not self.spec.usable or self._fetch is None:
            raise MemoryUnavailable(
                f"La mémoire « {self.spec.id} » est déclarée mais pas encore "
                f"branchée (statut : {self.spec.status}). Source réelle : "
                f"{self.spec.source or 'inconnue'}.")
        manquantes = [k for k in self.spec.required_keys if k not in kwargs]
        if manquantes:
            raise MemoryError(
                f"Lecture de « {self.spec.id} » incomplète : "
                f"{', '.join(manquantes)} manquant(s).")
        return self._fetch(**kwargs)

    def describe(self) -> dict:
        return self.spec.describe()


class MemoryRegistry:
    def __init__(self) -> None:
        self._memories: Dict[str, RegisteredMemory] = {}

    def register(self, spec: MemorySpec, fetch: Optional[Callable] = None) -> RegisteredMemory:
        if spec.id in self._memories:
            raise ValueError(
                f"Mémoire « {spec.id} » déjà enregistrée : deux mécanismes "
                f"sous un même identifiant se masqueraient silencieusement.")
        entry = RegisteredMemory(spec, fetch)
        self._memories[spec.id] = entry
        return entry

    def get(self, memory_id: str) -> RegisteredMemory:
        try:
            return self._memories[memory_id]
        except KeyError:
            connues = ', '.join(sorted(self._memories)) or '(aucune)'
            raise MemoryNotFound(
                f"Mémoire inconnue : « {memory_id} ». Déclarées : {connues}."
            ) from None

    def fetch(self, memory_id: str, **kwargs) -> MemoryEntry:
        return self.get(memory_id).fetch(**kwargs)

    def all(self) -> Tuple[RegisteredMemory, ...]:
        return tuple(self._memories[k] for k in sorted(self._memories))

    def available(self) -> Tuple[RegisteredMemory, ...]:
        return tuple(m for m in self.all() if m.spec.usable)

    def describe(self, usable_only: bool = False) -> list:
        source = self.available() if usable_only else self.all()
        return [m.describe() for m in source]

    def __contains__(self, memory_id: str) -> bool:
        return memory_id in self._memories

    def __len__(self) -> int:
        return len(self._memories)


registry = MemoryRegistry()
