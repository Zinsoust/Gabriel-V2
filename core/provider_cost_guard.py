"""Fail-closed financial guard for every paid provider attempt.

The guard is deliberately disabled by default.  When enabled it requires the
transactional credit ledger, explicit operation quotes, explicit provider
prices and persistent PostgreSQL budget RPCs.  No in-memory counter is treated
as a financial authority.

Routes create one :class:`FinancialOperation`; every physical provider request
then reserves its worst-case cost atomically before network I/O.  Retries and
fallbacks are therefore independent billable attempts.  Known usage is settled
at its configured price; missing usage uses the conservative reservation.
Interrupted requests remain uncertain and can never release credits silently.
"""

from __future__ import annotations

import contextvars
import hashlib
import json
import math
import os
import threading
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_CEILING
from typing import Any, Iterator, Mapping, Optional

from core.credit_ledger import credit_ledger_enabled


_TRUE = {"1", "true", "yes", "on"}
_FIXED_COST_PROVIDERS = {"elevenlabs", "rapidapi", "youtube"}


class FinancialGuardError(RuntimeError):
    """Base class for safe, non-provider financial failures."""


class FinancialConfigurationError(FinancialGuardError):
    """The guard was enabled without a complete, coherent configuration."""


class FinancialLimitExceeded(FinancialGuardError):
    """A user, provider or operation budget cannot fund another attempt."""


class FinancialStoreUnavailable(FinancialGuardError):
    """Persistent financial state could not be verified."""


class UnprotectedProviderCall(FinancialGuardError):
    """A paid call reached the common client without an operation context."""


class FinancialReplayBlocked(FinancialGuardError):
    """A persisted operation key was replayed and must not spend again."""


@dataclass(frozen=True)
class ModelPrice:
    input_microusd_per_million: int = 0
    output_microusd_per_million: int = 0
    fixed_max_microusd: Optional[int] = None


@dataclass(frozen=True)
class OperationQuote:
    credits: int
    provider_budget_microusd: int
    pricing_version: str


@dataclass(frozen=True)
class FinancialConfig:
    input_margin: Decimal
    prices: Mapping[str, Mapping[str, ModelPrice]]
    operations: Mapping[str, OperationQuote]


@dataclass(frozen=True)
class AttemptHandle:
    operation: "FinancialOperation"
    attempt_no: int
    provider: str
    model: str
    label: str
    max_cost_microusd: int
    price: ModelPrice


def provider_cost_guard_enabled(env: Optional[Mapping[str, str]] = None) -> bool:
    source = os.environ if env is None else env
    return str(source.get("GABRIEL_PROVIDER_COST_GUARD_ENABLED", "false")).strip().lower() in _TRUE


def paid_provider_calls_enabled(env: Optional[Mapping[str, str]] = None) -> bool:
    """Return whether deployed code may reach a paid provider.

    Development keeps its historical opt-out behaviour. On Render or an
    explicitly production-labelled process, paid traffic is disabled unless a
    separate switch is deliberately enabled. This makes an incomplete beta
    configuration fail before network I/O instead of silently spending money.
    """
    source = os.environ if env is None else env
    deployed = (
        bool(source.get("RENDER"))
        or str(source.get("GABRIEL_ENV", "")).strip().lower() == "production"
    )
    if not deployed:
        return True
    return str(source.get("GABRIEL_PAID_AI_ENABLED", "false")).strip().lower() in _TRUE


def _positive_int(value: Any, name: str) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise FinancialConfigurationError(f"{name} doit etre un entier positif") from exc
    if parsed <= 0:
        raise FinancialConfigurationError(f"{name} doit etre un entier positif")
    return parsed


def _usd_to_microusd(value: Any, name: str, *, allow_zero: bool = False) -> int:
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise FinancialConfigurationError(f"{name} invalide") from exc
    if not parsed.is_finite() or parsed < 0 or (not allow_zero and parsed == 0):
        raise FinancialConfigurationError(f"{name} invalide")
    result = int((parsed * Decimal("1000000")).to_integral_value(rounding=ROUND_CEILING))
    if result < 0 or (not allow_zero and result == 0):
        raise FinancialConfigurationError(f"{name} trop faible")
    return result


def _load_json(env: Mapping[str, str], key: str) -> dict:
    raw = str(env.get(key, "") or "").strip()
    if not raw:
        raise FinancialConfigurationError(f"{key} requis")
    try:
        value = json.loads(raw)
    except (TypeError, json.JSONDecodeError) as exc:
        raise FinancialConfigurationError(f"{key} invalide") from exc
    if not isinstance(value, dict) or not value:
        raise FinancialConfigurationError(f"{key} doit etre un objet JSON non vide")
    return value


def load_financial_config(env: Optional[Mapping[str, str]] = None) -> Optional[FinancialConfig]:
    source = os.environ if env is None else env
    if not provider_cost_guard_enabled(source):
        return None
    if not credit_ledger_enabled(dict(source)):
        raise FinancialConfigurationError(
            "GABRIEL_CREDIT_LEDGER_ENABLED doit etre true avec le garde de cout"
        )
    if str(source.get("MISTRAL_VALIDATION_BUDGET_ENABLED", "false")).lower() in _TRUE:
        raise FinancialConfigurationError(
            "le budget de validation Mistral et le garde applicatif ne peuvent pas etre actifs ensemble"
        )

    try:
        margin = Decimal(str(source.get("GABRIEL_PROVIDER_INPUT_TOKEN_MARGIN", "1.25")))
    except InvalidOperation as exc:
        raise FinancialConfigurationError("GABRIEL_PROVIDER_INPUT_TOKEN_MARGIN invalide") from exc
    if not margin.is_finite() or margin < 1:
        raise FinancialConfigurationError("GABRIEL_PROVIDER_INPUT_TOKEN_MARGIN doit etre >= 1")

    raw_prices = _load_json(source, "GABRIEL_PROVIDER_PRICING_JSON")
    prices: dict[str, dict[str, ModelPrice]] = {}
    for provider, models in raw_prices.items():
        name = str(provider).strip().lower()
        if not name or not isinstance(models, dict) or not models:
            raise FinancialConfigurationError(f"tarifs fournisseur invalides: {name}")
        prices[name] = {}
        for model, values in models.items():
            if not isinstance(values, dict):
                raise FinancialConfigurationError(f"tarif modele invalide: {name}/{model}")
            model_name = str(model).strip()
            fixed = values.get("max_attempt_usd")
            if fixed is not None:
                prices[name][model_name] = ModelPrice(
                    fixed_max_microusd=_usd_to_microusd(
                        fixed, f"{name}/{model_name}.max_attempt_usd"
                    )
                )
                continue
            if name in _FIXED_COST_PROVIDERS:
                raise FinancialConfigurationError(
                    f"{name}/{model_name}.max_attempt_usd requis"
                )
            input_rate = _usd_to_microusd(
                values.get("input_usd_per_million"),
                f"{name}/{model_name}.input_usd_per_million",
                allow_zero=True,
            )
            output_rate = _usd_to_microusd(
                values.get("output_usd_per_million"),
                f"{name}/{model_name}.output_usd_per_million",
                allow_zero=True,
            )
            if input_rate == 0 and output_rate == 0:
                raise FinancialConfigurationError(f"tarif nul interdit: {name}/{model_name}")
            prices[name][model_name] = ModelPrice(input_rate, output_rate)

    raw_operations = _load_json(source, "GABRIEL_AI_OPERATION_BUDGETS_JSON")
    operations: dict[str, OperationQuote] = {}
    for operation, values in raw_operations.items():
        if not isinstance(values, dict):
            raise FinancialConfigurationError(f"bareme operation invalide: {operation}")
        op_name = str(operation).strip()
        version = str(values.get("pricing_version", "") or "").strip()
        if not op_name or not version:
            raise FinancialConfigurationError(f"operation ou pricing_version vide: {operation}")
        operations[op_name] = OperationQuote(
            credits=_positive_int(values.get("credits"), f"{op_name}.credits"),
            provider_budget_microusd=_usd_to_microusd(
                values.get("provider_budget_usd"), f"{op_name}.provider_budget_usd"
            ),
            pricing_version=version,
        )

    return FinancialConfig(margin, prices, operations)


class SupabaseFinancialBackend:
    """Service-role-only RPC adapter; secrets never leave the server process."""

    def __init__(self, client: Any):
        self._client = client

    @classmethod
    def from_env(cls, env: Optional[Mapping[str, str]] = None) -> "SupabaseFinancialBackend":
        source = os.environ if env is None else env
        url = str(source.get("SUPABASE_URL", "") or "").strip()
        key = str(source.get("SUPABASE_SERVICE_ROLE_KEY", "") or "").strip()
        if not url or not key:
            raise FinancialConfigurationError(
                "SUPABASE_URL et SUPABASE_SERVICE_ROLE_KEY sont requis pour le ledger"
            )
        try:
            from supabase import ClientOptions, create_client
            client = create_client(
                url, key, options=ClientOptions(postgrest_client_timeout=30)
            )
        except Exception as exc:
            raise FinancialStoreUnavailable("client financier Supabase indisponible") from exc
        return cls(client)

    def _rpc(self, name: str, params: dict[str, Any]) -> dict[str, Any]:
        try:
            data = self._client.rpc(name, params).execute().data
        except Exception as exc:
            message = str(exc).lower()
            if "budget" in message or "insufficient" in message or "p0001" in message:
                raise FinancialLimitExceeded("budget ou credits insuffisants") from exc
            raise FinancialStoreUnavailable(f"RPC financiere indisponible: {name}") from exc
        if isinstance(data, list):
            data = data[0] if data else None
        if not isinstance(data, dict):
            raise FinancialStoreUnavailable(f"reponse RPC financiere invalide: {name}")
        return data

    def reserve_operation(self, **params: Any) -> dict[str, Any]:
        return self._rpc("gabriel_credit_reserve", params)

    def reserve_attempt(self, **params: Any) -> dict[str, Any]:
        return self._rpc("gabriel_provider_budget_reserve_attempt", params)

    def settle_attempt(self, **params: Any) -> dict[str, Any]:
        return self._rpc("gabriel_provider_budget_settle_attempt", params)

    def capture(self, **params: Any) -> dict[str, Any]:
        return self._rpc("gabriel_credit_capture", params)

    def release(self, **params: Any) -> dict[str, Any]:
        return self._rpc("gabriel_credit_release", params)

    def mark_uncertain(self, **params: Any) -> dict[str, Any]:
        return self._rpc("gabriel_credit_mark_uncertain", params)


class DisabledFinancialOperation:
    enabled = False
    detached = False
    attempts_started = 0

    def bind(self):
        return _bind_operation(self)

    def finalize_success(self) -> None:
        return None

    def finalize_failure(self) -> None:
        return None


class FinancialOperation:
    enabled = True

    def __init__(self, *, config: FinancialConfig, backend: Any, user_id: str,
                 operation_type: str, idempotency_key: str, request_hash: str):
        if not user_id:
            raise FinancialConfigurationError("identite utilisateur requise")
        try:
            quote = config.operations[operation_type]
        except KeyError as exc:
            raise FinancialConfigurationError(
                f"aucun bareme explicite pour l'operation {operation_type}"
            ) from exc
        self.config = config
        self.backend = backend
        self.user_id = str(user_id)
        self.operation_type = operation_type
        self.idempotency_key = str(idempotency_key)
        self.request_hash = str(request_hash)
        self.quote = quote
        self.reservation_id: Optional[str] = None
        self.attempts_started = 0
        self._attempt_max_total_microusd = 0
        self._settled_microusd = 0
        self._uncertain_microusd = 0
        self._attempt_lock = threading.Lock()
        self._finalized = False
        self.detached = False

    def bind(self):
        return _bind_operation(self)

    def _ensure_reserved(self) -> None:
        if self.reservation_id:
            return
        row = self.backend.reserve_operation(
            p_authenticated_user_id=self.user_id,
            p_user_id=self.user_id,
            p_operation_type=self.operation_type,
            p_idempotency_key=self.idempotency_key,
            p_request_hash=self.request_hash,
            p_credits=self.quote.credits,
            p_provider_budget_micros=self.quote.provider_budget_microusd,
            p_pricing_version=self.quote.pricing_version,
        )
        reservation_id = row.get("reservation_id")
        if not reservation_id:
            raise FinancialStoreUnavailable("reservation de credits sans identifiant")
        if row.get("idempotent") is True:
            raise FinancialReplayBlocked(
                "operation deja reservee; nouvelle depense fournisseur refusee"
            )
        self.reservation_id = str(reservation_id)

    def _price(self, provider: str, model: str) -> ModelPrice:
        try:
            return self.config.prices[provider][model]
        except KeyError as exc:
            raise FinancialConfigurationError(
                f"aucun tarif explicite pour {provider}/{model}"
            ) from exc

    def _max_cost(self, price: ModelPrice, input_text: str, max_output_tokens: int) -> int:
        if price.fixed_max_microusd is not None:
            return price.fixed_max_microusd
        # A byte-level upper bound is intentionally more conservative than the
        # usual ``characters / 4`` estimate.  Provider tokenizers can split
        # accents, JSON punctuation and identifiers much more densely; a cost
        # guard must reserve high, not merely predict the average.
        estimated_input = max(
            1,
            math.ceil(len(input_text.encode("utf-8")) * float(self.config.input_margin)),
        )
        output = _positive_int(max_output_tokens, "max_output_tokens")
        numerator = (
            estimated_input * price.input_microusd_per_million
            + output * price.output_microusd_per_million
        )
        return max(1, math.ceil(numerator / 1_000_000))

    def begin_attempt(self, *, provider: str, model: str, input_text: str,
                      max_output_tokens: int, label: str) -> AttemptHandle:
        provider_name = str(provider).strip().lower()
        price = self._price(provider_name, model)
        max_cost = self._max_cost(price, input_text, max_output_tokens)
        with self._attempt_lock:
            if self._finalized:
                raise FinancialGuardError("operation financiere deja finalisee")
            self._ensure_reserved()
            attempt_no = self.attempts_started + 1
            if self._attempt_max_total_microusd + max_cost > self.quote.provider_budget_microusd:
                raise FinancialLimitExceeded("plafond fournisseur de l'operation atteint")
            self.backend.reserve_attempt(
                p_authenticated_user_id=self.user_id,
                p_user_id=self.user_id,
                p_reservation_id=self.reservation_id,
                p_attempt_no=attempt_no,
                p_provider=provider_name,
                p_model=model,
                p_max_cost_micros=max_cost,
                p_provider_request_id=None,
            )
            self.attempts_started = attempt_no
            self._attempt_max_total_microusd += max_cost
        return AttemptHandle(self, attempt_no, provider_name, model, label, max_cost, price)

    def _actual_cost(self, attempt: AttemptHandle, response_model: str,
                     input_tokens: Optional[int], output_tokens: Optional[int]) -> int:
        if response_model != attempt.model:
            price = self._price(attempt.provider, response_model)
        else:
            price = attempt.price
        if price.fixed_max_microusd is not None:
            return attempt.max_cost_microusd
        if input_tokens is None or output_tokens is None:
            return attempt.max_cost_microusd
        actual = math.ceil((
            max(0, int(input_tokens)) * price.input_microusd_per_million
            + max(0, int(output_tokens)) * price.output_microusd_per_million
        ) / 1_000_000)
        if actual > attempt.max_cost_microusd:
            raise FinancialConfigurationError("cout reel superieur a la reservation conservatrice")
        return max(0, actual)

    def settle_success(self, attempt: AttemptHandle, *, response_model: str,
                       input_tokens: Optional[int], output_tokens: Optional[int]) -> None:
        try:
            actual = self._actual_cost(attempt, response_model, input_tokens, output_tokens)
        except Exception:
            self.settle_uncertain(attempt)
            raise
        try:
            self.backend.settle_attempt(
                p_authenticated_user_id=self.user_id,
                p_user_id=self.user_id,
                p_reservation_id=self.reservation_id,
                p_attempt_no=attempt.attempt_no,
                p_state="succeeded",
                p_actual_cost_micros=actual,
                p_input_tokens=input_tokens,
                p_output_tokens=output_tokens,
            )
        except Exception:
            # The provider has answered but persistence is uncertain.  Keep the
            # whole ceiling locally so finalisation can never release credits.
            with self._attempt_lock:
                self._uncertain_microusd += attempt.max_cost_microusd
            raise
        with self._attempt_lock:
            self._settled_microusd += actual

    def settle_uncertain(self, attempt: AttemptHandle) -> None:
        try:
            self.backend.settle_attempt(
                p_authenticated_user_id=self.user_id,
                p_user_id=self.user_id,
                p_reservation_id=self.reservation_id,
                p_attempt_no=attempt.attempt_no,
                p_state="uncertain",
                p_actual_cost_micros=None,
                p_input_tokens=None,
                p_output_tokens=None,
            )
        finally:
            with self._attempt_lock:
                self._uncertain_microusd += attempt.max_cost_microusd

    def finalize_success(self) -> None:
        with self._attempt_lock:
            if self._finalized:
                return
            self._finalized = True
        if not self.reservation_id:
            return
        if self._uncertain_microusd:
            self.backend.mark_uncertain(
                p_authenticated_user_id=self.user_id,
                p_user_id=self.user_id,
                p_reservation_id=self.reservation_id,
                p_uncertain_provider_micros=self._uncertain_microusd,
            )
            return
        self.backend.capture(
            p_authenticated_user_id=self.user_id,
            p_user_id=self.user_id,
            p_reservation_id=self.reservation_id,
            p_captured_credits=self.quote.credits,
            p_provider_spent_micros=self._settled_microusd,
        )

    def finalize_failure(self) -> None:
        with self._attempt_lock:
            if self._finalized:
                return
            self._finalized = True
        if not self.reservation_id:
            return
        if self.attempts_started == 0:
            self.backend.release(
                p_authenticated_user_id=self.user_id,
                p_user_id=self.user_id,
                p_reservation_id=self.reservation_id,
            )
        elif self._uncertain_microusd:
            self.backend.mark_uncertain(
                p_authenticated_user_id=self.user_id,
                p_user_id=self.user_id,
                p_reservation_id=self.reservation_id,
                p_uncertain_provider_micros=self._uncertain_microusd,
            )
        else:
            self.backend.capture(
                p_authenticated_user_id=self.user_id,
                p_user_id=self.user_id,
                p_reservation_id=self.reservation_id,
                p_captured_credits=0,
                p_provider_spent_micros=self._settled_microusd,
            )


_current_operation: contextvars.ContextVar[Any] = contextvars.ContextVar(
    "gabriel_financial_operation", default=None
)
_backend_override: Any = None


def set_financial_backend_for_tests(backend: Any) -> None:
    global _backend_override
    _backend_override = backend


def reset_financial_backend_for_tests() -> None:
    global _backend_override
    _backend_override = None


def create_financial_operation(*, user_id: str, operation_type: str,
                               idempotency_key: Optional[str], request_hash: str,
                               env: Optional[Mapping[str, str]] = None) -> Any:
    config = load_financial_config(env)
    if config is None:
        return DisabledFinancialOperation()
    key = str(idempotency_key or uuid.uuid4())
    backend = _backend_override or SupabaseFinancialBackend.from_env(env)
    return FinancialOperation(
        config=config,
        backend=backend,
        user_id=user_id,
        operation_type=operation_type,
        idempotency_key=key,
        request_hash=request_hash,
    )


@contextmanager
def _bind_operation(operation: Any) -> Iterator[Any]:
    token = _current_operation.set(operation)
    try:
        yield operation
    finally:
        _current_operation.reset(token)


def current_financial_operation() -> Any:
    return _current_operation.get()


def begin_provider_attempt(*, provider: str, model: str, input_text: str,
                           max_output_tokens: int, label: str = "") -> Optional[AttemptHandle]:
    if not paid_provider_calls_enabled():
        raise FinancialConfigurationError(
            "appels fournisseurs payants desactives sur cet environnement"
        )
    if not provider_cost_guard_enabled():
        return None
    operation = current_financial_operation()
    if operation is None or not getattr(operation, "enabled", False):
        raise UnprotectedProviderCall(
            f"appel fournisseur sans operation financiere: {provider}/{label or model}"
        )
    return operation.begin_attempt(
        provider=provider,
        model=model,
        input_text=input_text,
        max_output_tokens=max_output_tokens,
        label=label,
    )


def settle_provider_success(attempt: Optional[AttemptHandle], *, response_model: str,
                            input_tokens: Optional[int], output_tokens: Optional[int]) -> None:
    if attempt is not None:
        attempt.operation.settle_success(
            attempt,
            response_model=response_model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )


def settle_provider_failure(attempt: Optional[AttemptHandle]) -> None:
    if attempt is not None:
        attempt.operation.settle_uncertain(attempt)


def submit_with_financial_context(executor: Any, fn: Any, /, *args: Any, **kwargs: Any):
    """Submit work while preserving the immutable operation reference.

    ``contextvars`` do not propagate to ``ThreadPoolExecutor`` automatically.
    Each submitted callable receives its own copied context, while sharing the
    operation's locked attempt counter and persistent PostgreSQL authority.
    """
    context = contextvars.copy_context()
    return executor.submit(context.run, fn, *args, **kwargs)


def request_fingerprint(method: str, path: str, body: bytes) -> str:
    digest = hashlib.sha256()
    digest.update(str(method).upper().encode("utf-8"))
    digest.update(b"\0")
    digest.update(str(path).encode("utf-8"))
    digest.update(b"\0")
    digest.update(body or b"")
    return digest.hexdigest()
