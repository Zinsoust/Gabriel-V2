"""Point d'entrée unique vers les fournisseurs de LLM.

PURPOSE
    Découpler Gabriel du fournisseur de modèle. Avant ce module, trois
    implémentations séparées appelaient le SDK Mistral avec des timeouts, des
    politiques de réessai et des constantes de modèle différentes — et l'une
    d'elles s'appelait ``_call_claude`` alors qu'elle appelait Mistral.

RESPONSIBILITIES
    - exposer une interface fournisseur (``LLMProvider``) et son implémentation Mistral ;
    - appliquer une politique de réessai explicite et paramétrable ;
    - appliquer les garde-fous de débit (espacement + plafond de concurrence) ;
    - renvoyer une réponse normalisée (texte + métriques d'usage).

NON-RESPONSIBILITIES
    - ne construit aucun prompt (c'est le rôle des agents/skills) ;
    - ne parse aucun JSON métier (voir ``core.security.safe_parse_ai_json``) ;
    - ne connaît aucune logique business (audience, stratégie, contenu).

INPUTS   prompt (str) + politique d'appel (modèle, tokens, timeout, réessais)
OUTPUTS  ``LLMResponse`` (texte, modèle réellement appelé, tokens, troncature)
DEPENDS  mistralai (SDK), variables d'environnement MISTRAL_*
"""

from __future__ import annotations

import os
import random
import threading
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional


# ── Politique de modèle ──────────────────────────────────────────────────────
# Source de vérité unique des modèles réellement appelés. Tout ``model_version``
# persisté ailleurs doit lire CES constantes, jamais une variable
# d'environnement séparée qui pourrait diverger de ce qui part vraiment.
MODEL_TIERS = {
    "fast": "mistral-small-latest",   # classification, extraction, reformulation
    "deep": "mistral-large-latest",   # analyse, arbitrage, stratégie, critique
}


def model_for_tier(tier: str) -> str:
    """Traduit un palier logique en identifiant de modèle concret."""
    try:
        return MODEL_TIERS[tier]
    except KeyError:
        raise ValueError(f"Palier de modèle inconnu : {tier!r} (attendu : {sorted(MODEL_TIERS)})")


# ── Contrat de réponse ───────────────────────────────────────────────────────

@dataclass
class LLMResponse:
    """Réponse normalisée, indépendante du fournisseur."""
    text: str
    model: str
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    finish_reason: Optional[str] = None

    @property
    def truncated(self) -> bool:
        """Vrai si le modèle a été coupé par la limite de tokens — un JSON
        produit dans ce cas est presque toujours incomplet."""
        return self.finish_reason in ("length", "model_length")


# ── Politique de réessai ─────────────────────────────────────────────────────

@dataclass(frozen=True)
class RetryPolicy:
    """Décrit quand et comment réessayer. Volontairement explicite : un réessai
    aveugle sur une erreur d'entrée invalide ne fait que gaspiller du temps."""
    max_attempts: int = 2
    base_delay: float = 4.0
    max_delay: float = 16.0
    exponential: bool = False
    jitter: bool = False
    retry_on_status: tuple = (429, 529)

    def delay_for(self, attempt: int) -> float:
        if self.exponential:
            delay = min(2 ** attempt, self.max_delay)
        else:
            delay = self.base_delay
        if self.jitter:
            delay += random.uniform(0, 1.5)
        return delay


# Politique historique du pipeline Psychologue : forte pression de parallélisme
# (jusqu'à 6 appels simultanés), donc réessais nombreux avec backoff.
RETRY_RESILIENT = RetryPolicy(max_attempts=6, exponential=True, jitter=True)

# Politique historique de Stratège / Créateur : appels isolés, un seul réessai.
RETRY_SIMPLE = RetryPolicy(max_attempts=2, base_delay=4.0)

# Aucun réessai : sites qui préfèrent échouer vite et se rabattre sur une
# réponse de secours plutôt que faire attendre l'utilisateur (voix, rendu
# de ton — où une seconde d'attente se remarque).
RETRY_NONE = RetryPolicy(max_attempts=1)


# ── Garde-fous de débit (partagés par tout le processus) ─────────────────────
# Deux leviers complémentaires : le sémaphore plafonne les appels SIMULTANÉS,
# le throttle espace les LANCEMENTS (le vrai levier contre une limite
# « requêtes/seconde »).
_MAX_CONCURRENCY = int(os.environ.get("MISTRAL_MAX_CONCURRENCY", "4"))
_MIN_INTERVAL = float(os.environ.get("MISTRAL_MIN_INTERVAL", "0.5"))
_semaphore = threading.Semaphore(_MAX_CONCURRENCY)
_rate_lock = threading.Lock()
_last_launch = [0.0]


def _throttle():
    """Espace les lancements, tous threads confondus. Appelé AVANT le sémaphore
    pour ne pas consommer un créneau de concurrence pendant l'attente."""
    with _rate_lock:
        now = time.time()
        wait = _MIN_INTERVAL - (now - _last_launch[0])
        if wait > 0:
            time.sleep(wait)
            now = time.time()
        _last_launch[0] = now


# ── Interface fournisseur ────────────────────────────────────────────────────

class LLMProvider(ABC):
    """Contrat que doit remplir tout fournisseur de LLM.

    Ajouter un fournisseur (OpenAI, Anthropic, local…) = implémenter cette
    classe, sans toucher aux agents ni à l'orchestrateur.
    """

    name: str = "abstract"

    @abstractmethod
    def complete(self, prompt: str, *, model: str, max_tokens: int,
                 temperature: Optional[float] = None,
                 timeout_ms: int = 300_000,
                 system: Optional[str] = None) -> LLMResponse:
        """Un aller-retour avec le modèle. Lève en cas d'échec — la politique de
        réessai est appliquée par ``complete()`` au niveau du module, pas ici.

        ``system`` porte les instructions de rôle, séparées de la demande. Les
        mélanger au prompt utilisateur affaiblit la frontière que la couche de
        sécurité pose entre consigne et contenu non fiable."""
        raise NotImplementedError


class MistralProvider(LLMProvider):
    """Implémentation Mistral. Seul fournisseur câblé aujourd'hui."""

    name = "mistral"

    def complete(self, prompt: str, *, model: str, max_tokens: int,
                 temperature: Optional[float] = None,
                 timeout_ms: int = 300_000,
                 system: Optional[str] = None) -> LLMResponse:
        try:
            from mistralai import Mistral
        except ImportError as err:  # pragma: no cover - dépend de l'installation
            raise ImportError(
                "Le SDK 'mistralai' installé est incompatible (classe 'Mistral' "
                "introuvable). Ce projet requiert mistralai==1.10.0 (voir "
                "requirements.txt) — vérifiez qu'aucune dépendance ne force une "
                "autre version, et videz le cache de build en production."
            ) from err
        key = os.environ.get("MISTRAL_API_KEY")
        if not key:
            raise RuntimeError(
                "MISTRAL_API_KEY manquante — configurez-la dans les variables d'environnement."
            )
        client = Mistral(api_key=key, timeout_ms=timeout_ms)
        # temperature=None → défaut du modèle (comportement historique).
        extra = {} if temperature is None else {
            "temperature": max(0.0, min(1.0, float(temperature)))
        }
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        response = client.chat.complete(
            model=model,
            max_tokens=max_tokens,
            messages=messages,
            **extra,
        )
        choice = response.choices[0]
        usage = response.usage
        return LLMResponse(
            text=(choice.message.content or "").strip(),
            model=model,
            prompt_tokens=getattr(usage, "prompt_tokens", None) if usage else None,
            completion_tokens=getattr(usage, "completion_tokens", None) if usage else None,
            finish_reason=getattr(choice, "finish_reason", None),
        )


_default_provider: LLMProvider = MistralProvider()


def get_provider() -> LLMProvider:
    return _default_provider


def set_provider(provider: LLMProvider) -> None:
    """Remplace le fournisseur par défaut — utilisé par les tests et, à terme,
    par un routeur de modèle."""
    global _default_provider
    _default_provider = provider


# ── Point d'entrée unique ────────────────────────────────────────────────────

def complete(prompt: str, *, tier: str = "deep", max_tokens: int = 5000,
             temperature: Optional[float] = None, timeout_ms: int = 300_000,
             retry: RetryPolicy = RETRY_SIMPLE, label: str = "",
             throttled: bool = True, provider: Optional[LLMProvider] = None,
             system: Optional[str] = None) -> LLMResponse:
    """Appelle un LLM avec réessais, garde-fous de débit et journalisation.

    ``throttled=False`` désactive l'espacement/plafond de concurrence pour un
    appel isolé et synchrone (ex. Stratège), où la file d'attente n'apporterait
    que de la latence sans protéger de quoi que ce soit.
    """
    engine = provider or _default_provider
    model = model_for_tier(tier)

    for attempt in range(retry.max_attempts):
        try:
            if throttled:
                _throttle()
                waited_from = time.time()
                _semaphore.acquire()
                waited = time.time() - waited_from
                if waited > 1.0:
                    print(f"[LLM] label={label or '?'} attente_file={waited:.2f}s "
                          f"({_MAX_CONCURRENCY} créneaux partagés par toute l'app)")
            try:
                response = engine.complete(
                    prompt, model=model, max_tokens=max_tokens,
                    temperature=temperature, timeout_ms=timeout_ms,
                    system=system,
                )
            finally:
                if throttled:
                    _semaphore.release()

            if response.prompt_tokens is not None:
                print(f"[LLM] label={label or '?'} provider={engine.name} model={model} "
                      f"prompt_tokens={response.prompt_tokens} "
                      f"completion_tokens={response.completion_tokens} "
                      f"max_tokens={max_tokens} finish_reason={response.finish_reason}")
            if response.truncated:
                print(f"[LLM_TRUNCATION] label={label or '?'} model={model} max_tokens={max_tokens} "
                      f"completion_tokens={response.completion_tokens} "
                      f"— réponse coupée, JSON probablement incomplet")
            return response

        except Exception as exc:
            status = getattr(exc, "status_code", None) or getattr(exc, "http_status", None)
            is_last = attempt >= retry.max_attempts - 1
            if status in retry.retry_on_status and not is_last:
                delay = retry.delay_for(attempt)
                print(f"[LLM_RETRY] label={label or '?'} status={status} "
                      f"tentative={attempt + 1}/{retry.max_attempts} → nouvel essai dans {delay:.1f}s")
                time.sleep(delay)
                continue
            raise


def complete_text(prompt: str, **kwargs) -> str:
    """Variante confort : renvoie directement le texte.

    Utile pour les sites d'appel historiques qui n'exploitaient que la chaîne.
    """
    return complete(prompt, **kwargs).text
