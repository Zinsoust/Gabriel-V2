"""Critique adverse — penser contre sa propre production.

Gabriel pratique déjà cette discipline à deux endroits : le Stratège fait
challenger sa stratégie par un second appel contrarien, le Créateur attaque son
propre texte avant de le livrer. Les deux partagent une *méthode*, pas du code :

    produire → soumettre à un examinateur qui cherche la faille →
    en tirer un verdict structuré → ne jamais laisser cet examen casser
    la production principale.

Ce module extrait cette enveloppe commune, et **rien d'autre**. Ce qui diffère
reste chez chaque agent, parce que ces différences sont réelles, pas
accidentelles :

* les schémas de sortie (six champs stratégiques contre une liste de
  faiblesses typées) ;
* les vocabulaires de verdict (« solide / à ajuster / fragile » contre
  « livrable / a_ameliorer ») ;
* les clients LLM et les parseurs — celui du Stratège lève en cas d'échec,
  celui du Créateur dégrade pour rendre au moins le texte brut ;
* les politiques d'échec — le Stratège se passe de la critique, le Créateur
  lui substitue un objet neutre qui laisse passer le texte.

Fusionner ces sorties changerait ce que produisent les deux agents. Le Critic
uniformise donc la *démarche*, jamais le résultat.
"""

from dataclasses import dataclass, field
from typing import Callable, Dict, Optional, Tuple


class CriticError(RuntimeError):
    """Erreur de la couche Critic.

    Hérite de RuntimeError : c'est ce que propageait le Stratège, et un
    appelant qui l'attrapait par ce type doit continuer à le faire.
    """


class CritiqueNotFound(CriticError, KeyError):
    """Aucune critique déclarée sous cet identifiant."""


# Issues possibles d'une critique.
CRITIQUE_OK = 'ok'                # exploitable et complète
CRITIQUE_INCOMPLETE = 'incomplete'  # exploitable, mais des champs manquent
CRITIQUE_FAILED = 'failed'        # inexploitable — repli appliqué


@dataclass(frozen=True)
class CritiqueSpec:
    """Ce qu'on attend d'un examen critique donné."""

    id: str
    name: str
    domain: str
    expected_keys: Tuple[str, ...] = ()
    verdict_key: str = 'verdict'
    # Verdicts signifiant « la production peut partir telle quelle ».
    passing_verdicts: Tuple[str, ...] = ()
    # Ce qu'on renvoie quand l'examen échoue. `None` = laisser l'erreur
    # remonter, l'appelant décidant seul (comportement du Stratège).
    fallback: Optional[Dict] = None
    # Mise en forme propre à l'agent, appliquée au résultat exploitable.
    normalize: Optional[Callable[[Dict], Dict]] = None
    log_prefix: str = 'CRITIC'

    def describe(self) -> dict:
        return {
            'id': self.id,
            'name': self.name,
            'domain': self.domain,
            'expected_keys': list(self.expected_keys),
            'verdict_key': self.verdict_key,
            'passing_verdicts': list(self.passing_verdicts),
            'blocking': self.fallback is None,
        }


@dataclass(frozen=True)
class Critique:
    """Le résultat d'un examen."""

    spec_id: str
    data: Dict = field(default_factory=dict)
    status: str = CRITIQUE_OK
    missing_keys: Tuple[str, ...] = ()
    error: str = ''
    verdict_key: str = 'verdict'
    passing_verdicts: Tuple[str, ...] = ()

    @property
    def verdict(self) -> str:
        return self.data.get(self.verdict_key, '') or ''

    @property
    def usable(self) -> bool:
        """L'examen a produit quelque chose d'exploitable."""
        return self.status != CRITIQUE_FAILED

    @property
    def passed(self) -> bool:
        """La production peut partir sans retouche.

        Une critique qui a échoué ne vaut pas approbation : ne pas avoir
        d'objection parce qu'on n'a pas pu regarder n'est pas la même chose que
        ne pas en avoir après avoir regardé.
        """
        return self.usable and self.verdict in self.passing_verdicts

    def describe(self) -> dict:
        return {
            'spec_id': self.spec_id,
            'status': self.status,
            'verdict': self.verdict,
            'passed': self.passed,
            'missing_keys': list(self.missing_keys),
            'error': self.error,
        }


def _missing(data: Dict, expected: Tuple[str, ...]) -> Tuple[str, ...]:
    """Champs absents ou vides. Zéro compte comme une valeur : un score de
    confiance nul est une réponse, pas une omission."""
    return tuple(k for k in expected
                 if not data.get(k) and data.get(k) != 0)


class Critic:
    """Déroule un examen critique selon sa fiche."""

    def review(self, spec: CritiqueSpec, prompt: str, *,
               call_llm: Callable, parse_json: Callable,
               max_tokens: int = 1500, **llm_kwargs) -> Critique:
        """Soumet une production déjà faite à un second regard.

        Le client LLM et le parseur sont injectés : chaque agent garde les
        siens, avec ses réglages mesurés en production (modèle, timeout,
        température). Les imposer ici casserait ce qui a été calibré.
        """
        def _echec(message: str) -> Critique:
            if spec.fallback is None:
                raise CriticError(message)
            print(f"[{spec.log_prefix}] critique ignorée : {message}")
            return Critique(spec.id, dict(spec.fallback), CRITIQUE_FAILED,
                            error=message, verdict_key=spec.verdict_key,
                            passing_verdicts=spec.passing_verdicts)

        try:
            raw = call_llm(prompt, max_tokens=max_tokens, **llm_kwargs)
            data = parse_json(raw)
        except Exception as error:      # noqa: BLE001 — l'examen ne doit jamais
            return _echec(str(error))   # faire tomber la production principale

        if not isinstance(data, dict) or data.get('parse_error'):
            return _echec("réponse inexploitable du modèle")

        if spec.normalize is not None:
            data = spec.normalize(data)

        manquants = _missing(data, spec.expected_keys)
        if manquants:
            print(f"[{spec.log_prefix}] Critique incomplète — "
                  f"clefs manquantes={list(manquants)} "
                  f"(JSON probablement tronqué puis réparé)")

        return Critique(
            spec.id, data,
            CRITIQUE_INCOMPLETE if manquants else CRITIQUE_OK,
            missing_keys=manquants, verdict_key=spec.verdict_key,
            passing_verdicts=spec.passing_verdicts)


class CriticRegistry:
    def __init__(self) -> None:
        self._specs: Dict[str, CritiqueSpec] = {}

    def register(self, spec: CritiqueSpec) -> CritiqueSpec:
        if spec.id in self._specs:
            raise ValueError(
                f"Critique « {spec.id} » déjà enregistrée : deux examens sous "
                f"un même identifiant se masqueraient silencieusement.")
        self._specs[spec.id] = spec
        return spec

    def get(self, spec_id: str) -> CritiqueSpec:
        try:
            return self._specs[spec_id]
        except KeyError:
            connus = ', '.join(sorted(self._specs)) or '(aucune)'
            raise CritiqueNotFound(
                f"Critique inconnue : « {spec_id} ». Déclarées : {connus}."
            ) from None

    def all(self) -> Tuple[CritiqueSpec, ...]:
        return tuple(self._specs[k] for k in sorted(self._specs))

    def describe(self) -> list:
        return [s.describe() for s in self.all()]

    def __contains__(self, spec_id: str) -> bool:
        return spec_id in self._specs

    def __len__(self) -> int:
        return len(self._specs)


registry = CriticRegistry()
critic = Critic()
