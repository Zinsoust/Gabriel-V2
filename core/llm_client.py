"""Point d'entrée unique vers les fournisseurs de LLM.

PURPOSE
    Découpler Gabriel du fournisseur de modèle. Avant ce module, trois
    implémentations séparées appelaient le SDK Mistral avec des timeouts, des
    politiques de réessai et des constantes de modèle différentes — et l'une
    d'elles s'appelait ``_call_claude`` alors qu'elle appelait Mistral.

RESPONSIBILITIES
    - exposer une interface fournisseur (``LLMProvider``) et ses implémentations
      (Mistral, OpenAI) ;
    - choisir le fournisseur actif (variable ``LLM_PROVIDER``) ;
    - traduire un palier logique (rapide / profond) vers le catalogue du
      fournisseur retenu ;
    - appliquer une politique de réessai explicite et paramétrable ;
    - appliquer les garde-fous de débit (espacement + plafond de concurrence) ;
    - renvoyer une réponse normalisée (texte + métriques d'usage).

NON-RESPONSIBILITIES
    - ne construit aucun prompt (c'est le rôle des agents/skills) ;
    - ne parse aucun JSON métier (voir ``core.security.safe_parse_ai_json``) ;
    - ne connaît aucune logique business (audience, stratégie, contenu).

INPUTS   prompt (str) + politique d'appel (palier, tokens, timeout, réessais)
OUTPUTS  ``LLMResponse`` (texte, modèle réellement appelé, tokens, troncature)
DEPENDS  mistralai (SDK) ou requests (OpenAI) selon le fournisseur actif ;
         variables d'environnement MISTRAL_*, OPENAI_*, LLM_PROVIDER

HORS PÉRIMÈTRE
    L'appel OpenAI de l'orchestrateur conversationnel (``app.py``) reste
    séparé : il utilise l'API Responses avec un historique multi-tours, un
    effort de raisonnement et une recherche web hébergée. Cette dernière est
    une capacité d'outil, pas de génération — la modéliser ici obligerait
    *tout* fournisseur à l'implémenter.
"""

from __future__ import annotations

import os
import random
import threading
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional

from core.llm_budget import MistralBudgetGuard


# ── Politique de modèle ──────────────────────────────────────────────────────
# Source de vérité unique des modèles réellement appelés. Tout ``model_version``
# persisté ailleurs doit lire CES constantes, jamais une variable
# d'environnement séparée qui pourrait diverger de ce qui part vraiment.
# Surchargeables par l'environnement : l'abonnement Mistral peut retirer un
# modèle du jour au lendemain (13/09/2026 : mistral-small passé à 0 requête/min,
# toute analyse échouait en 429). On bascule alors sans toucher au code.
def _tiers_from_env(env=None) -> dict:
    env = os.environ if env is None else env
    return {
        "fast": env.get("MISTRAL_MODEL_FAST") or "mistral-small-latest",   # classification, extraction, reformulation
        "deep": env.get("MISTRAL_MODEL_DEEP") or "mistral-large-latest",   # analyse, arbitrage, stratégie, critique
    }


MODEL_TIERS = _tiers_from_env()


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
#
# Défauts abaissés (4→2, 0.5s→1.0s) après un diagnostic en conditions réelles :
# le compte Mistral configuré renvoie une 403 "tier_not_allowed" — un message
# qui ressemble à un modèle interdit, mais qui apparaît aussi sur mistral-small
# (censé être accessible) dès que plusieurs appels partent en même temps. Testé
# en direct : un appel "deep" isolé échoue toujours (modèle réellement hors
# palier), mais une rafale de 8 appels "fast" simultanés en perd ~5 en 403,
# alors que la même rafale sérialisée à 2 passe intégralement (0 échec sur 22
# appels, y compris 2 analyses lancées en même temps). Le vrai plafond du
# compte est donc un plafond de CONCURRENCE, pas seulement de modèle.
_MAX_CONCURRENCY = int(os.environ.get("MISTRAL_MAX_CONCURRENCY", "2"))
_MIN_INTERVAL = float(os.environ.get("MISTRAL_MIN_INTERVAL", "1.0"))
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

class ProviderHTTPError(RuntimeError):
    """Échec HTTP d'un fournisseur, normalisé.

    Chaque transport signale un statut à sa manière (attribut du SDK, réponse
    ``requests``…). La politique de réessai ne doit pas connaître ces
    variantes : elle lit toujours ``status_code``.
    """

    def __init__(self, status_code: Optional[int], message: str):
        super().__init__(message)
        self.status_code = status_code


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
                 system: Optional[str] = None,
                 json_mode: bool = False) -> LLMResponse:
        """Un aller-retour avec le modèle. Lève en cas d'échec — la politique de
        réessai est appliquée par ``complete()`` au niveau du module, pas ici.

        ``system`` porte les instructions de rôle, séparées de la demande. Les
        mélanger au prompt utilisateur affaiblit la frontière que la couche de
        sécurité pose entre consigne et contenu non fiable.

        ``json_mode`` demande au fournisseur une sortie JSON syntaxiquement
        valide (mode natif ``json_object``). Sans lui, un petit modèle glisse du
        markdown dans le JSON et la réparation tolérante avale des champs entiers."""
        raise NotImplementedError


class MistralProvider(LLMProvider):
    """Implémentation Mistral. Seul fournisseur câblé aujourd'hui."""

    name = "mistral"

    def complete(self, prompt: str, *, model: str, max_tokens: int,
                 temperature: Optional[float] = None,
                 timeout_ms: int = 300_000,
                 system: Optional[str] = None,
                 json_mode: bool = False) -> LLMResponse:
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
        if json_mode:
            extra["response_format"] = {"type": "json_object"}
        response = client.chat.complete(
            model=model,
            max_tokens=max_tokens,
            messages=messages,
            # Every physical request must be preceded by a ledger reservation.
            # Disable SDK-level retries so only the retry loop in complete()
            # can issue another billed request.
            retries=None,
            **extra,
        )
        choice = response.choices[0]
        usage = response.usage
        return LLMResponse(
            text=(choice.message.content or "").strip(),
            # Preserve the provider-reported model when available so the
            # validation budget can detect an unexpected server-side fallback.
            model=getattr(response, "model", None) or model,
            prompt_tokens=getattr(usage, "prompt_tokens", None) if usage else None,
            completion_tokens=getattr(usage, "completion_tokens", None) if usage else None,
            finish_reason=getattr(choice, "finish_reason", None),
        )


class OpenAIProvider(LLMProvider):
    """Implémentation OpenAI via l'API Chat Completions.

    Volontairement limitée au contrat agent (une consigne, une demande, une
    réponse). L'orchestrateur conversationnel a des besoins plus riches
    (historique multi-tours, effort de raisonnement, recherche web hébergée)
    qui relèvent d'un outil et non du contrat de génération — les modéliser
    ici alourdirait l'interface que doit implémenter *tout* fournisseur.

    Pas de SDK : le projet appelle déjà OpenAI en HTTP direct, inutile
    d'ajouter une dépendance pour un seul appel.
    """

    name = "openai"

    # Paliers propres au fournisseur : un « palier rapide » ne désigne pas le
    # même modèle d'un fournisseur à l'autre.
    MODELS = {
        "fast": os.environ.get("OPENAI_MODEL_FAST", "gpt-4o-mini"),
        "deep": os.environ.get("OPENAI_MODEL_DEEP", "gpt-4o"),
    }

    def complete(self, prompt: str, *, model: str, max_tokens: int,
                 temperature: Optional[float] = None,
                 timeout_ms: int = 300_000,
                 system: Optional[str] = None,
                 json_mode: bool = False) -> LLMResponse:
        import requests

        key = os.environ.get("OPENAI_API_KEY")
        if not key:
            raise RuntimeError(
                "OPENAI_API_KEY manquante — configurez-la dans les variables d'environnement."
            )

        # ``model`` arrive traduit par le palier Mistral : on retraduit vers
        # l'équivalent OpenAI plutôt que d'envoyer un nom que l'API refuserait.
        target = self.MODELS.get(_tier_of_model(model), self.MODELS["deep"])

        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        payload = {"model": target, "messages": messages, "max_tokens": max_tokens}
        if temperature is not None:
            payload["temperature"] = max(0.0, min(1.0, float(temperature)))
        if json_mode:
            payload["response_format"] = {"type": "json_object"}

        try:
            response = requests.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                json=payload,
                timeout=timeout_ms / 1000,
            )
        except requests.RequestException as err:
            raise ProviderHTTPError(None, f"OpenAI injoignable : {err}") from err

        if response.status_code >= 400:
            raise ProviderHTTPError(
                response.status_code,
                f"OpenAI a répondu {response.status_code} : {response.text[:200]}",
            )

        data = response.json()
        choice = (data.get("choices") or [{}])[0]
        usage = data.get("usage") or {}
        return LLMResponse(
            text=((choice.get("message") or {}).get("content") or "").strip(),
            model=target,
            prompt_tokens=usage.get("prompt_tokens"),
            completion_tokens=usage.get("completion_tokens"),
            finish_reason=choice.get("finish_reason"),
        )


def _tier_of_model(model: str) -> str:
    """Retrouve le palier logique à partir d'un identifiant de modèle."""
    for tier, name in MODEL_TIERS.items():
        if name == model:
            return tier
    return "deep"


PROVIDERS = {
    "mistral": MistralProvider,
    "openai": OpenAIProvider,
}


def _provider_from_env() -> LLMProvider:
    """Le fournisseur par défaut est configurable sans toucher au code."""
    choice = os.environ.get("LLM_PROVIDER", "mistral").strip().lower()
    factory = PROVIDERS.get(choice)
    if factory is None:
        raise ValueError(
            f"LLM_PROVIDER inconnu : {choice!r} (attendu : {sorted(PROVIDERS)})"
        )
    return factory()


_default_provider: LLMProvider = _provider_from_env()


def get_provider() -> LLMProvider:
    return _default_provider


def set_provider(provider: LLMProvider) -> None:
    """Remplace le fournisseur par défaut — utilisé par les tests et, à terme,
    par un routeur de modèle."""
    global _default_provider
    _default_provider = provider


# ── Point d'entrée unique ────────────────────────────────────────────────────

_NETWORK_ERROR_NAMES = ("ConnectError", "ConnectTimeout", "ReadTimeout", "WriteTimeout", "PoolTimeout",
                        "RemoteProtocolError", "ReadError", "NetworkError", "TimeoutException")


def _is_network_error(exc: BaseException) -> bool:
    """Vrai pour une coupure réseau, y compris enveloppée par le SDK du fournisseur."""
    courant, vus = exc, 0
    while courant is not None and vus < 5:
        if isinstance(courant, (ConnectionError, TimeoutError)) or type(courant).__name__ in _NETWORK_ERROR_NAMES:
            return True
        courant, vus = courant.__cause__ or courant.__context__, vus + 1
    return False


def _accepts_json_mode(engine) -> bool:
    import inspect
    try:
        params = inspect.signature(engine.complete).parameters
    except (TypeError, ValueError):
        return False
    return "json_mode" in params or any(p.kind is p.VAR_KEYWORD for p in params.values())


def complete(prompt: str, *, tier: str = "deep", max_tokens: int = 5000,
             temperature: Optional[float] = None, timeout_ms: int = 300_000,
             retry: RetryPolicy = RETRY_SIMPLE, label: str = "",
             throttled: bool = True, provider: Optional[LLMProvider] = None,
             system: Optional[str] = None, json_mode: bool = False) -> LLMResponse:
    """Appelle un LLM avec réessais, garde-fous de débit et journalisation.

    ``throttled=False`` désactive l'espacement/plafond de concurrence pour un
    appel isolé et synchrone (ex. Stratège), où la file d'attente n'apporterait
    que de la latence sans protéger de quoi que ce soit.
    """
    engine = provider or _default_provider
    model = model_for_tier(tier)
    budget_guard = MistralBudgetGuard.from_env()
    if budget_guard:
        budget_guard.require_mistral_provider(engine.name)
    budget_input = (system or "") + "\n" + prompt

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
                reservation = None
                if budget_guard:
                    reservation = budget_guard.reserve(
                        model=model,
                        input_text=budget_input,
                        max_output_tokens=max_tokens,
                        label=label,
                        attempt_number=attempt + 1,
                    )
                # json_mode n'est transmis qu'aux fournisseurs qui le connaissent :
                # un fournisseur tiers continue de fonctionner à l'identique (la
                # réparation JSON tolérante reste alors le filet de sécurité).
                extra = {"json_mode": True} if json_mode and _accepts_json_mode(engine) else {}
                try:
                    response = engine.complete(
                        prompt, model=model, max_tokens=max_tokens,
                        temperature=temperature, timeout_ms=timeout_ms,
                        system=system, **extra,
                    )
                except BaseException as exc:
                    if budget_guard and reservation:
                        budget_guard.mark_uncertain(reservation, type(exc).__name__)
                    raise
                if budget_guard and reservation:
                    budget_guard.settle(
                        reservation,
                        response_model=response.model,
                        input_tokens=response.prompt_tokens,
                        output_tokens=response.completion_tokens,
                    )
            finally:
                if throttled:
                    _semaphore.release()

            # On journalise le modèle RÉELLEMENT appelé (response.model), pas
            # celui demandé : un fournisseur retraduit le palier vers son
            # propre catalogue, et afficher le nom d'entrée ferait croire
            # qu'un modèle Mistral a répondu alors qu'OpenAI a servi l'appel.
            if response.prompt_tokens is not None:
                print(f"[LLM] label={label or '?'} provider={engine.name} model={response.model} "
                      f"prompt_tokens={response.prompt_tokens} "
                      f"completion_tokens={response.completion_tokens} "
                      f"max_tokens={max_tokens} finish_reason={response.finish_reason}")
            if response.truncated:
                print(f"[LLM_TRUNCATION] label={label or '?'} model={response.model} max_tokens={max_tokens} "
                      f"completion_tokens={response.completion_tokens} "
                      f"— réponse coupée, JSON probablement incomplet")
            return response

        except Exception as exc:
            status = getattr(exc, "status_code", None) or getattr(exc, "http_status", None)
            is_last = attempt >= retry.max_attempts - 1
            if status is None and _is_network_error(exc) and not is_last:
                # Coupure réseau (DNS, connexion refusée, délai) : le serveur du
                # modèle n'a rien reçu, réessayer ne coûte rien. Constaté le
                # 13/09/2026 sur une connexion partagée : deux créations
                # perdues sur un « nodename nor servname provided » passager.
                delay = retry.delay_for(attempt)
                print(f"[LLM_RETRY] label={label or '?'} réseau={type(exc).__name__} "
                      f"tentative={attempt + 1}/{retry.max_attempts} → nouvel essai dans {delay:.1f}s")
                time.sleep(delay)
                continue
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
