"""Persistent, conservative spending guard for controlled Mistral validation.

The guard is disabled by default. When enabled it reserves the worst-case
configured cost before every physical API attempt in a SQLite ledger. Failed,
interrupted, or unmetered attempts keep their full reservation because their
billing status cannot be proven locally.

This is a local safety control, not a billing authority: provider-side token
accounting, rounding, price changes, and infrastructure persistence remain
outside the process. A provider-side workspace spend limit is still required.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import time
import uuid
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_CEILING, ROUND_FLOOR
from pathlib import Path
from typing import Optional


_TRUE_VALUES = {"1", "true", "yes", "on"}
_RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
_SAFE_LABEL_RE = re.compile(r"[^A-Za-z0-9._:-]+")


class MistralBudgetError(RuntimeError):
    """Base class for validation-budget failures."""


class MistralBudgetConfigurationError(MistralBudgetError):
    """The strict validation mode is enabled but not safely configured."""


class MistralBudgetExceeded(MistralBudgetError):
    """The next API attempt cannot fit within the remaining reservation."""


@dataclass(frozen=True)
class ModelPrice:
    input_usd_per_million: Decimal
    output_usd_per_million: Decimal


@dataclass(frozen=True)
class BudgetConfig:
    run_id: str
    budget_microusd: int
    ledger_path: str
    input_margin: Decimal
    max_attempts: int
    prices: dict[str, ModelPrice]
    config_hash: str


@dataclass(frozen=True)
class Reservation:
    attempt_id: str
    run_id: str
    model: str
    reserved_microusd: int
    estimated_input_tokens: int
    max_output_tokens: int


def validation_budget_enabled(env=None) -> bool:
    env = os.environ if env is None else env
    return str(env.get("MISTRAL_VALIDATION_BUDGET_ENABLED", "false")).strip().lower() in _TRUE_VALUES


def _positive_decimal(value, name: str, *, allow_one: bool = False) -> Decimal:
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise MistralBudgetConfigurationError(f"{name} invalide") from exc
    minimum = Decimal("1") if allow_one else Decimal("0")
    if not parsed.is_finite() or (parsed < minimum if allow_one else parsed <= minimum):
        raise MistralBudgetConfigurationError(f"{name} invalide")
    return parsed


def _load_config(env=None) -> Optional[BudgetConfig]:
    env = os.environ if env is None else env
    if not validation_budget_enabled(env):
        return None

    run_id = str(env.get("MISTRAL_VALIDATION_RUN_ID", "") or "").strip()
    if not _RUN_ID_RE.fullmatch(run_id):
        raise MistralBudgetConfigurationError("MISTRAL_VALIDATION_RUN_ID absent ou invalide")

    budget_usd = _positive_decimal(env.get("MISTRAL_VALIDATION_BUDGET_USD"), "MISTRAL_VALIDATION_BUDGET_USD")
    budget_microusd = int((budget_usd * Decimal("1000000")).to_integral_value(rounding=ROUND_FLOOR))
    if budget_microusd <= 0:
        raise MistralBudgetConfigurationError("budget trop faible")

    ledger_raw = str(env.get("MISTRAL_VALIDATION_LEDGER_PATH", "") or "").strip()
    if not ledger_raw:
        raise MistralBudgetConfigurationError("MISTRAL_VALIDATION_LEDGER_PATH requis")
    ledger = Path(ledger_raw).expanduser()
    if not ledger.is_absolute():
        raise MistralBudgetConfigurationError("MISTRAL_VALIDATION_LEDGER_PATH doit etre absolu")

    margin = _positive_decimal(
        env.get("MISTRAL_VALIDATION_INPUT_MARGIN", "1.25"),
        "MISTRAL_VALIDATION_INPUT_MARGIN",
        allow_one=True,
    )
    try:
        max_attempts = int(env.get("MISTRAL_VALIDATION_MAX_ATTEMPTS", ""))
    except (TypeError, ValueError) as exc:
        raise MistralBudgetConfigurationError("MISTRAL_VALIDATION_MAX_ATTEMPTS invalide") from exc
    if max_attempts <= 0:
        raise MistralBudgetConfigurationError("MISTRAL_VALIDATION_MAX_ATTEMPTS invalide")

    try:
        price_data = json.loads(str(env.get("MISTRAL_VALIDATION_PRICING_JSON", "") or ""))
    except (json.JSONDecodeError, TypeError) as exc:
        raise MistralBudgetConfigurationError("MISTRAL_VALIDATION_PRICING_JSON invalide") from exc
    if not isinstance(price_data, dict) or not price_data:
        raise MistralBudgetConfigurationError("MISTRAL_VALIDATION_PRICING_JSON requis")

    prices: dict[str, ModelPrice] = {}
    canonical_prices = {}
    for model, values in price_data.items():
        model = str(model or "").strip()
        if not model or model.endswith("-latest") or not isinstance(values, dict):
            raise MistralBudgetConfigurationError("modele non fige ou tarif invalide")
        input_rate = _positive_decimal(values.get("input_usd_per_million"), f"tarif entree {model}")
        output_rate = _positive_decimal(values.get("output_usd_per_million"), f"tarif sortie {model}")
        prices[model] = ModelPrice(input_rate, output_rate)
        canonical_prices[model] = {
            "input_usd_per_million": str(input_rate),
            "output_usd_per_million": str(output_rate),
        }

    config_payload = json.dumps(
        {
            "input_margin": str(margin),
            "max_attempts": max_attempts,
            "prices": canonical_prices,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    config_hash = hashlib.sha256(config_payload.encode("utf-8")).hexdigest()
    return BudgetConfig(
        run_id=run_id,
        budget_microusd=budget_microusd,
        ledger_path=str(ledger),
        input_margin=margin,
        max_attempts=max_attempts,
        prices=prices,
        config_hash=config_hash,
    )


def _cost_microusd(input_tokens: int, output_tokens: int, price: ModelPrice) -> int:
    # With rates expressed in USD / million tokens, multiplying the token
    # count by that rate directly yields micro-USD.
    amount = Decimal(input_tokens) * price.input_usd_per_million
    amount += Decimal(output_tokens) * price.output_usd_per_million
    return int(amount.to_integral_value(rounding=ROUND_CEILING))


def _estimated_input_tokens(input_text: str, margin: Decimal) -> int:
    # UTF-8 bytes are a deliberately conservative tokenizer-independent upper
    # bound for ordinary text. The fixed overhead accounts for message framing.
    byte_count = len(str(input_text or "").encode("utf-8")) + 256
    return max(1, int((Decimal(byte_count) * margin).to_integral_value(rounding=ROUND_CEILING)))


class MistralBudgetGuard:
    def __init__(self, config: BudgetConfig):
        self.config = config
        parent = Path(config.ledger_path).parent
        parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    @classmethod
    def from_env(cls, env=None) -> Optional["MistralBudgetGuard"]:
        config = _load_config(env)
        return cls(config) if config else None

    def _connect(self):
        conn = sqlite3.connect(self.config.ledger_path, timeout=30, isolation_level=None)
        conn.execute("PRAGMA busy_timeout=30000")
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _initialize(self):
        with self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS mistral_budget_campaigns (
                    run_id TEXT PRIMARY KEY,
                    budget_microusd INTEGER NOT NULL,
                    config_hash TEXT NOT NULL,
                    created_at REAL NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS mistral_budget_attempts (
                    attempt_id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL,
                    provider TEXT NOT NULL,
                    model TEXT NOT NULL,
                    label TEXT NOT NULL,
                    attempt_number INTEGER NOT NULL,
                    estimated_input_tokens INTEGER NOT NULL,
                    max_output_tokens INTEGER NOT NULL,
                    reserved_microusd INTEGER NOT NULL,
                    actual_microusd INTEGER,
                    actual_input_tokens INTEGER,
                    actual_output_tokens INTEGER,
                    status TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    finished_at REAL,
                    FOREIGN KEY(run_id) REFERENCES mistral_budget_campaigns(run_id)
                )
            """)
            conn.execute(
                "INSERT OR IGNORE INTO mistral_budget_campaigns VALUES (?, ?, ?, ?)",
                (self.config.run_id, self.config.budget_microusd, self.config.config_hash, time.time()),
            )
            row = conn.execute(
                "SELECT budget_microusd, config_hash FROM mistral_budget_campaigns WHERE run_id = ?",
                (self.config.run_id,),
            ).fetchone()
            if row != (self.config.budget_microusd, self.config.config_hash):
                raise MistralBudgetConfigurationError(
                    "ce run_id existe deja avec un budget ou des tarifs differents"
                )

    def require_mistral_provider(self, provider_name: str):
        if provider_name != "mistral":
            raise MistralBudgetConfigurationError(
                "le mode de validation Mistral interdit tout fallback vers un autre fournisseur"
            )

    def reserve(self, *, model: str, input_text: str, max_output_tokens: int,
                label: str, attempt_number: int) -> Reservation:
        if model.endswith("-latest") or model not in self.config.prices:
            raise MistralBudgetConfigurationError(
                f"modele Mistral non fige ou sans tarif configure: {model}"
            )
        try:
            output_limit = int(max_output_tokens)
        except (TypeError, ValueError) as exc:
            raise MistralBudgetConfigurationError("max_output_tokens invalide") from exc
        if output_limit <= 0:
            raise MistralBudgetConfigurationError("max_output_tokens invalide")

        estimated_input = _estimated_input_tokens(input_text, self.config.input_margin)
        reserved = _cost_microusd(
            estimated_input, output_limit, self.config.prices[model]
        )
        attempt_id = str(uuid.uuid4())
        safe_label = _SAFE_LABEL_RE.sub("_", str(label or "unknown"))[:80] or "unknown"

        with self._connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            spent = conn.execute("""
                SELECT COALESCE(SUM(COALESCE(actual_microusd, reserved_microusd)), 0)
                FROM mistral_budget_attempts WHERE run_id = ?
            """, (self.config.run_id,)).fetchone()[0]
            attempt_count = conn.execute(
                "SELECT COUNT(*) FROM mistral_budget_attempts WHERE run_id = ?",
                (self.config.run_id,),
            ).fetchone()[0]
            if attempt_count >= self.config.max_attempts:
                conn.rollback()
                print(
                    f"[MISTRAL_BUDGET] run_id={self.config.run_id} status=attempt_limit "
                    f"model={model} label={safe_label} attempts={attempt_count}"
                )
                raise MistralBudgetExceeded(
                    "nombre maximal de tentatives Mistral atteint: appel refuse avant execution"
                )
            if spent + reserved > self.config.budget_microusd:
                conn.rollback()
                remaining = max(0, self.config.budget_microusd - spent)
                print(
                    f"[MISTRAL_BUDGET] run_id={self.config.run_id} status=exhausted "
                    f"model={model} label={safe_label} required_microusd={reserved} "
                    f"remaining_microusd={remaining}"
                )
                raise MistralBudgetExceeded(
                    "budget Mistral insuffisant: appel refuse avant execution"
                )
            conn.execute("""
                INSERT INTO mistral_budget_attempts (
                    attempt_id, run_id, provider, model, label, attempt_number,
                    estimated_input_tokens, max_output_tokens,
                    reserved_microusd, status, created_at
                ) VALUES (?, ?, 'mistral', ?, ?, ?, ?, ?, ?, 'reserved', ?)
            """, (
                attempt_id, self.config.run_id, model, safe_label,
                int(attempt_number), estimated_input, output_limit, reserved, time.time(),
            ))
            conn.commit()

        print(
            f"[MISTRAL_BUDGET] run_id={self.config.run_id} status=reserved "
            f"model={model} label={safe_label} attempt={attempt_number} "
            f"estimated_input_tokens={estimated_input} max_output_tokens={output_limit} "
            f"reserved_microusd={reserved}"
        )
        return Reservation(
            attempt_id, self.config.run_id, model, reserved,
            estimated_input, output_limit,
        )

    def mark_uncertain(self, reservation: Reservation, reason: str):
        status = "failed_uncertain_" + _SAFE_LABEL_RE.sub("_", str(reason or "error"))[:32]
        with self._connect() as conn:
            conn.execute("""
                UPDATE mistral_budget_attempts
                SET status = ?, finished_at = ?
                WHERE attempt_id = ? AND run_id = ? AND status = 'reserved'
            """, (status, time.time(), reservation.attempt_id, reservation.run_id))
        print(
            f"[MISTRAL_BUDGET] run_id={reservation.run_id} status={status} "
            f"model={reservation.model} reserved_microusd={reservation.reserved_microusd}"
        )

    def settle(self, reservation: Reservation, *, response_model: str,
               input_tokens, output_tokens):
        if response_model != reservation.model:
            self.mark_uncertain(reservation, "model_mismatch")
            raise MistralBudgetConfigurationError(
                "le fournisseur a retourne un modele different du modele reserve"
            )
        try:
            actual_input = int(input_tokens)
            actual_output = int(output_tokens)
        except (TypeError, ValueError):
            self.mark_uncertain(reservation, "usage_missing")
            return
        if actual_input < 0 or actual_output < 0:
            self.mark_uncertain(reservation, "usage_invalid")
            return

        actual = _cost_microusd(
            actual_input, actual_output, self.config.prices[reservation.model]
        )
        status = "settled"
        # Keep the higher amount if the provider reports usage beyond the
        # conservative reservation. This makes the breach visible and blocks
        # later calls rather than concealing it.
        accounted = max(actual, reservation.reserved_microusd) if (
            actual_input > reservation.estimated_input_tokens
            or actual_output > reservation.max_output_tokens
        ) else actual
        if accounted > reservation.reserved_microusd:
            status = "settled_reservation_breached"
        with self._connect() as conn:
            conn.execute("""
                UPDATE mistral_budget_attempts
                SET actual_microusd = ?, actual_input_tokens = ?,
                    actual_output_tokens = ?, status = ?, finished_at = ?
                WHERE attempt_id = ? AND run_id = ? AND status = 'reserved'
            """, (
                accounted, actual_input, actual_output, status, time.time(),
                reservation.attempt_id, reservation.run_id,
            ))
        print(
            f"[MISTRAL_BUDGET] run_id={reservation.run_id} status={status} "
            f"model={reservation.model} input_tokens={actual_input} "
            f"output_tokens={actual_output} accounted_microusd={accounted}"
        )

    def accounted_microusd(self) -> int:
        with self._connect() as conn:
            return int(conn.execute("""
                SELECT COALESCE(SUM(COALESCE(actual_microusd, reserved_microusd)), 0)
                FROM mistral_budget_attempts WHERE run_id = ?
            """, (self.config.run_id,)).fetchone()[0])
