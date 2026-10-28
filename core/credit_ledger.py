"""Transactional credit-ledger primitives for Gabriel.

Phase 1 deliberately keeps this module disconnected from HTTP routes.  The
SQLite implementation is a persistent local reference used by the test suite;
production wiring will call the PostgreSQL RPCs defined by the matching
Supabase migration.
"""

from __future__ import annotations

import json
import os
import sqlite3
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator


FEATURE_FLAG = "GABRIEL_CREDIT_LEDGER_ENABLED"
FINAL_RESERVATION_STATES = frozenset({"captured", "released"})
GRANT_SOURCE_TYPES = frozenset(
    {"legacy_migration", "signup", "subscription", "topup", "refund", "adjustment"}
)


class CreditLedgerError(RuntimeError):
    """Base class for ledger failures that are safe to expose to callers."""


class IdentityMismatch(CreditLedgerError):
    """The authenticated identity does not own the requested operation."""


class InsufficientCredits(CreditLedgerError):
    """The account cannot fund the requested reservation."""


class IdempotencyConflict(CreditLedgerError):
    """An idempotency key was reused for a different request."""


class InvalidLedgerState(CreditLedgerError):
    """The requested transition is not legal from the current state."""


def credit_ledger_enabled(environ: dict[str, str] | None = None) -> bool:
    """Return whether the future route integration is explicitly enabled.

    The default is deliberately fail-safe: importing this module never enables
    the ledger or changes the current credit flow.
    """

    source = os.environ if environ is None else environ
    return str(source.get(FEATURE_FLAG, "false")).strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalise_expiry(value: datetime | str | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).isoformat()
    return str(value)


class SQLiteCreditLedger:
    """Persistent, transactional reference ledger for local validation.

    A file path is mandatory so restart behaviour is testable and no implicit
    application database can be created.  Each operation opens its own
    connection and uses ``BEGIN IMMEDIATE``; concurrent writers therefore
    serialize before checking a balance.
    """

    def __init__(self, database_path: str | os.PathLike[str]):
        self.database_path = str(Path(database_path))
        if self.database_path == ":memory:":
            raise ValueError("a persistent SQLite path is required")
        Path(self.database_path).parent.mkdir(parents=True, exist_ok=True)
        self._initialise()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(
            self.database_path,
            timeout=10,
            isolation_level=None,
            check_same_thread=False,
        )
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA busy_timeout = 10000")
        return conn

    @contextmanager
    def _transaction(self) -> Iterator[sqlite3.Connection]:
        conn = self._connect()
        try:
            for attempt in range(8):
                try:
                    conn.execute("BEGIN IMMEDIATE")
                    break
                except sqlite3.OperationalError as exc:
                    if "locked" not in str(exc).lower() or attempt == 7:
                        raise
                    time.sleep(0.01 * (attempt + 1))
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
    def _initialise(self) -> None:
        conn = self._connect()
        try:
            conn.execute("PRAGMA journal_mode = WAL")
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS credit_accounts (
                    user_id TEXT PRIMARY KEY,
                    available_credits INTEGER NOT NULL DEFAULT 0 CHECK (available_credits >= 0),
                    reserved_credits INTEGER NOT NULL DEFAULT 0 CHECK (reserved_credits >= 0),
                    lifetime_granted INTEGER NOT NULL DEFAULT 0 CHECK (lifetime_granted >= 0),
                    lifetime_captured INTEGER NOT NULL DEFAULT 0 CHECK (lifetime_captured >= 0),
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS credit_grants (
                    grant_id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL REFERENCES credit_accounts(user_id),
                    source_type TEXT NOT NULL CHECK (source_type IN (
                        'legacy_migration','signup','subscription','topup','refund','adjustment'
                    )),
                    source_key TEXT NOT NULL,
                    granted_credits INTEGER NOT NULL CHECK (granted_credits > 0),
                    remaining_credits INTEGER NOT NULL CHECK (remaining_credits >= 0),
                    reserved_credits INTEGER NOT NULL DEFAULT 0 CHECK (reserved_credits >= 0),
                    starts_at TEXT NOT NULL,
                    expires_at TEXT,
                    expired_at TEXT,
                    expiration_cutoff TEXT,
                    metadata TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    UNIQUE (user_id, source_key),
                    CHECK (remaining_credits + reserved_credits <= granted_credits),
                    CHECK (
                        (expired_at IS NULL AND expiration_cutoff IS NULL)
                        OR
                        (expired_at IS NOT NULL AND expiration_cutoff IS NOT NULL)
                    )
                );

                CREATE TABLE IF NOT EXISTS legacy_snapshots (
                    user_id TEXT PRIMARY KEY REFERENCES credit_accounts(user_id),
                    legacy_credits INTEGER NOT NULL CHECK (legacy_credits >= 0),
                    snapshot_key TEXT NOT NULL UNIQUE,
                    imported_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS credit_reservations (
                    reservation_id TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL REFERENCES credit_accounts(user_id),
                    operation_type TEXT NOT NULL,
                    idempotency_key TEXT NOT NULL,
                    request_hash TEXT NOT NULL,
                    pricing_version TEXT NOT NULL,
                    quoted_credits INTEGER NOT NULL CHECK (quoted_credits > 0),
                    provider_budget_micros INTEGER NOT NULL CHECK (provider_budget_micros >= 0),
                    provider_spent_micros INTEGER NOT NULL DEFAULT 0 CHECK (provider_spent_micros >= 0),
                    uncertain_provider_micros INTEGER NOT NULL DEFAULT 0 CHECK (uncertain_provider_micros >= 0),
                    captured_credits INTEGER NOT NULL DEFAULT 0 CHECK (captured_credits >= 0),
                    status TEXT NOT NULL CHECK (status IN ('reserved','running','uncertain','captured','released')),
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    finalised_at TEXT,
                    UNIQUE (user_id, idempotency_key),
                    CHECK (captured_credits <= quoted_credits)
                );

                CREATE TABLE IF NOT EXISTS credit_allocations (
                    reservation_id TEXT NOT NULL REFERENCES credit_reservations(reservation_id),
                    grant_id TEXT NOT NULL REFERENCES credit_grants(grant_id),
                    reserved_credits INTEGER NOT NULL CHECK (reserved_credits > 0),
                    captured_credits INTEGER NOT NULL DEFAULT 0 CHECK (captured_credits >= 0),
                    released_credits INTEGER NOT NULL DEFAULT 0 CHECK (released_credits >= 0),
                    expired_credits INTEGER NOT NULL DEFAULT 0 CHECK (expired_credits >= 0),
                    PRIMARY KEY (reservation_id, grant_id),
                    CHECK (
                        captured_credits + released_credits + expired_credits
                        <= reserved_credits
                    )
                );

                CREATE TABLE IF NOT EXISTS provider_usage (
                    usage_id TEXT PRIMARY KEY,
                    reservation_id TEXT NOT NULL REFERENCES credit_reservations(reservation_id),
                    attempt_no INTEGER NOT NULL CHECK (attempt_no > 0),
                    provider TEXT NOT NULL,
                    model TEXT NOT NULL,
                    state TEXT NOT NULL CHECK (state IN ('started','succeeded','failed','uncertain')),
                    max_cost_micros INTEGER NOT NULL CHECK (max_cost_micros >= 0),
                    actual_cost_micros INTEGER CHECK (actual_cost_micros >= 0),
                    input_tokens INTEGER CHECK (input_tokens >= 0),
                    output_tokens INTEGER CHECK (output_tokens >= 0),
                    provider_request_id TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE (reservation_id, attempt_no),
                    UNIQUE (provider, provider_request_id)
                );

                CREATE TABLE IF NOT EXISTS credit_ledger_events (
                    sequence_no INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_id TEXT NOT NULL UNIQUE,
                    user_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    grant_id TEXT,
                    reservation_id TEXT,
                    delta_available INTEGER NOT NULL DEFAULT 0,
                    delta_reserved INTEGER NOT NULL DEFAULT 0,
                    delta_consumed INTEGER NOT NULL DEFAULT 0,
                    provider_micros INTEGER NOT NULL DEFAULT 0,
                    metadata TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL
                );

                CREATE TRIGGER IF NOT EXISTS credit_ledger_events_no_update
                BEFORE UPDATE ON credit_ledger_events
                BEGIN
                    SELECT RAISE(ABORT, 'credit ledger is append-only');
                END;

                CREATE TRIGGER IF NOT EXISTS credit_ledger_events_no_delete
                BEFORE DELETE ON credit_ledger_events
                BEGIN
                    SELECT RAISE(ABORT, 'credit ledger is append-only');
                END;
                """
            )
            grant_columns = {
                row["name"]
                for row in conn.execute("PRAGMA table_info(credit_grants)").fetchall()
            }
            if "expired_at" not in grant_columns:
                conn.execute("ALTER TABLE credit_grants ADD COLUMN expired_at TEXT")
            if "expiration_cutoff" not in grant_columns:
                conn.execute("ALTER TABLE credit_grants ADD COLUMN expiration_cutoff TEXT")

            allocation_columns = {
                row["name"]
                for row in conn.execute("PRAGMA table_info(credit_allocations)").fetchall()
            }
            if "expired_credits" not in allocation_columns:
                conn.execute(
                    """ALTER TABLE credit_allocations
                       ADD COLUMN expired_credits INTEGER NOT NULL DEFAULT 0
                       CHECK (expired_credits >= 0)"""
                )

            conn.execute(
                """UPDATE credit_grants
                   SET expired_at = (
                           SELECT MIN(event.created_at)
                           FROM credit_ledger_events AS event
                           WHERE event.grant_id = credit_grants.grant_id
                             AND event.event_type = 'expire'
                       ),
                       expiration_cutoff = expires_at
                   WHERE expired_at IS NULL
                     AND EXISTS (
                         SELECT 1
                         FROM credit_ledger_events AS event
                         WHERE event.grant_id = credit_grants.grant_id
                           AND event.event_type = 'expire'
                     )"""
            )
        finally:
            conn.close()
    @staticmethod
    def _authorise(authenticated_user_id: str, user_id: str) -> str:
        actor = str(authenticated_user_id or "").strip()
        owner = str(user_id or "").strip()
        if not actor or actor != owner:
            raise IdentityMismatch("authenticated user does not own this ledger operation")
        return owner

    @staticmethod
    def _ensure_account(conn: sqlite3.Connection, user_id: str, now: str) -> None:
        conn.execute(
            """INSERT OR IGNORE INTO credit_accounts
               (user_id, created_at, updated_at) VALUES (?, ?, ?)""",
            (user_id, now, now),
        )

    @staticmethod
    def _event(
        conn: sqlite3.Connection,
        *,
        user_id: str,
        event_type: str,
        grant_id: str | None = None,
        reservation_id: str | None = None,
        delta_available: int = 0,
        delta_reserved: int = 0,
        delta_consumed: int = 0,
        provider_micros: int = 0,
        metadata: dict[str, Any] | None = None,
        now: str,
    ) -> None:
        conn.execute(
            """INSERT INTO credit_ledger_events
               (event_id, user_id, event_type, grant_id, reservation_id,
                delta_available, delta_reserved, delta_consumed,
                provider_micros, metadata, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                str(uuid.uuid4()),
                user_id,
                event_type,
                grant_id,
                reservation_id,
                delta_available,
                delta_reserved,
                delta_consumed,
                provider_micros,
                json.dumps(metadata or {}, sort_keys=True),
                now,
            ),
        )

    def grant(
        self,
        *,
        authenticated_user_id: str,
        user_id: str,
        credits: int,
        source_type: str,
        source_key: str,
        expires_at: datetime | str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        owner = self._authorise(authenticated_user_id, user_id)
        if int(credits) <= 0 or source_type not in GRANT_SOURCE_TYPES or not source_key:
            raise ValueError("positive credits, source_type and source_key are required")
        credits = int(credits)
        expiry = _normalise_expiry(expires_at)
        metadata_json = json.dumps(metadata or {}, sort_keys=True)
        now = _utcnow()
        with self._transaction() as conn:
            self._ensure_account(conn, owner, now)
            existing = conn.execute(
                "SELECT * FROM credit_grants WHERE user_id = ? AND source_key = ?",
                (owner, source_key),
            ).fetchone()
            if existing:
                if (
                    existing["granted_credits"] != credits
                    or existing["source_type"] != source_type
                    or existing["expires_at"] != expiry
                ):
                    raise IdempotencyConflict("grant source key already has different terms")
                return {**dict(existing), "idempotent": True}

            grant_id = str(uuid.uuid4())
            conn.execute(
                """INSERT INTO credit_grants
                   (grant_id, user_id, source_type, source_key, granted_credits,
                    remaining_credits, starts_at, expires_at, metadata, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    grant_id,
                    owner,
                    source_type,
                    source_key,
                    credits,
                    credits,
                    now,
                    expiry,
                    metadata_json,
                    now,
                ),
            )
            conn.execute(
                """UPDATE credit_accounts
                   SET available_credits = available_credits + ?,
                       lifetime_granted = lifetime_granted + ?, updated_at = ?
                   WHERE user_id = ?""",
                (credits, credits, now, owner),
            )
            self._event(
                conn,
                user_id=owner,
                event_type="grant",
                grant_id=grant_id,
                delta_available=credits,
                metadata={"source_type": source_type, "source_key": source_key},
                now=now,
            )
            row = conn.execute(
                "SELECT * FROM credit_grants WHERE grant_id = ?", (grant_id,)
            ).fetchone()
            return {**dict(row), "idempotent": False}

    def import_legacy_balance(
        self,
        *,
        authenticated_user_id: str,
        user_id: str,
        legacy_credits: int,
        snapshot_key: str,
    ) -> dict[str, Any]:
        owner = self._authorise(authenticated_user_id, user_id)
        if int(legacy_credits) < 0 or not snapshot_key:
            raise ValueError("legacy balance must be non-negative and snapshot_key required")
        legacy_credits = int(legacy_credits)
        now = _utcnow()
        with self._transaction() as conn:
            self._ensure_account(conn, owner, now)
            existing = conn.execute(
                "SELECT * FROM legacy_snapshots WHERE user_id = ?", (owner,)
            ).fetchone()
            if existing:
                if (
                    existing["legacy_credits"] != legacy_credits
                    or existing["snapshot_key"] != snapshot_key
                ):
                    raise IdempotencyConflict("legacy balance was already snapshotted")
                account = conn.execute(
                    "SELECT * FROM credit_accounts WHERE user_id = ?", (owner,)
                ).fetchone()
                return {**dict(account), "idempotent": True}

            conn.execute(
                """INSERT INTO legacy_snapshots
                   (user_id, legacy_credits, snapshot_key, imported_at)
                   VALUES (?, ?, ?, ?)""",
                (owner, legacy_credits, snapshot_key, now),
            )
            if legacy_credits:
                grant_id = str(uuid.uuid4())
                source_key = f"legacy:{snapshot_key}"
                conn.execute(
                    """INSERT INTO credit_grants
                       (grant_id, user_id, source_type, source_key,
                        granted_credits, remaining_credits, starts_at,
                        metadata, created_at)
                       VALUES (?, ?, 'legacy_migration', ?, ?, ?, ?, ?, ?)""",
                    (
                        grant_id,
                        owner,
                        source_key,
                        legacy_credits,
                        legacy_credits,
                        now,
                        json.dumps({"snapshot_key": snapshot_key}, sort_keys=True),
                        now,
                    ),
                )
                conn.execute(
                    """UPDATE credit_accounts
                       SET available_credits = available_credits + ?,
                           lifetime_granted = lifetime_granted + ?, updated_at = ?
                       WHERE user_id = ?""",
                    (legacy_credits, legacy_credits, now, owner),
                )
                self._event(
                    conn,
                    user_id=owner,
                    event_type="legacy_import",
                    grant_id=grant_id,
                    delta_available=legacy_credits,
                    metadata={"snapshot_key": snapshot_key},
                    now=now,
                )
            account = conn.execute(
                "SELECT * FROM credit_accounts WHERE user_id = ?", (owner,)
            ).fetchone()
            return {**dict(account), "idempotent": False}

    def reserve(
        self,
        *,
        authenticated_user_id: str,
        user_id: str,
        operation_type: str,
        idempotency_key: str,
        request_hash: str,
        credits: int,
        provider_budget_micros: int,
        pricing_version: str = "phase1-provisional",
    ) -> dict[str, Any]:
        owner = self._authorise(authenticated_user_id, user_id)
        credits = int(credits)
        provider_budget_micros = int(provider_budget_micros)
        if credits <= 0 or provider_budget_micros < 0:
            raise ValueError("positive credits and non-negative provider budget required")
        if not operation_type or not idempotency_key or not request_hash or not pricing_version:
            raise ValueError("operation, idempotency key and request hash are required")
        now = _utcnow()
        with self._transaction() as conn:
            existing = conn.execute(
                """SELECT * FROM credit_reservations
                   WHERE user_id = ? AND idempotency_key = ?""",
                (owner, idempotency_key),
            ).fetchone()
            if existing:
                signature = (
                    existing["operation_type"],
                    existing["request_hash"],
                    existing["pricing_version"],
                    existing["quoted_credits"],
                    existing["provider_budget_micros"],
                )
                requested = (
                    operation_type,
                    request_hash,
                    pricing_version,
                    credits,
                    provider_budget_micros,
                )
                if signature != requested:
                    raise IdempotencyConflict("idempotency key belongs to another request")
                return {**dict(existing), "idempotent": True}

            account = conn.execute(
                "SELECT * FROM credit_accounts WHERE user_id = ?", (owner,)
            ).fetchone()
            if not account or account["available_credits"] < credits:
                raise InsufficientCredits("insufficient available credits")

            reservation_id = str(uuid.uuid4())
            conn.execute(
                """INSERT INTO credit_reservations
                   (reservation_id, user_id, operation_type, idempotency_key,
                    request_hash, pricing_version, quoted_credits, provider_budget_micros,
                    status, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'reserved', ?, ?)""",
                (
                    reservation_id,
                    owner,
                    operation_type,
                    idempotency_key,
                    request_hash,
                    pricing_version,
                    credits,
                    provider_budget_micros,
                    now,
                    now,
                ),
            )

            remaining = credits
            grants = conn.execute(
                """SELECT * FROM credit_grants
                   WHERE user_id = ? AND remaining_credits > 0
                     AND (expires_at IS NULL OR expires_at > ?)
                   ORDER BY CASE WHEN expires_at IS NULL THEN 1 ELSE 0 END,
                            expires_at, created_at, grant_id""",
                (owner, now),
            ).fetchall()
            for grant in grants:
                if not remaining:
                    break
                allocated = min(remaining, grant["remaining_credits"])
                conn.execute(
                    """UPDATE credit_grants
                       SET remaining_credits = remaining_credits - ?,
                           reserved_credits = reserved_credits + ?
                       WHERE grant_id = ?""",
                    (allocated, allocated, grant["grant_id"]),
                )
                conn.execute(
                    """INSERT INTO credit_allocations
                       (reservation_id, grant_id, reserved_credits)
                       VALUES (?, ?, ?)""",
                    (reservation_id, grant["grant_id"], allocated),
                )
                remaining -= allocated
            if remaining:
                raise InvalidLedgerState("account and grant balances diverged")

            conn.execute(
                """UPDATE credit_accounts
                   SET available_credits = available_credits - ?,
                       reserved_credits = reserved_credits + ?, updated_at = ?
                   WHERE user_id = ?""",
                (credits, credits, now, owner),
            )
            self._event(
                conn,
                user_id=owner,
                event_type="reserve",
                reservation_id=reservation_id,
                delta_available=-credits,
                delta_reserved=credits,
                provider_micros=provider_budget_micros,
                metadata={"operation_type": operation_type},
                now=now,
            )
            row = conn.execute(
                "SELECT * FROM credit_reservations WHERE reservation_id = ?",
                (reservation_id,),
            ).fetchone()
            return {**dict(row), "idempotent": False}

    def record_provider_attempt(
        self,
        *,
        authenticated_user_id: str,
        user_id: str,
        reservation_id: str,
        attempt_no: int,
        provider: str,
        model: str,
        max_cost_micros: int,
        provider_request_id: str | None = None,
    ) -> dict[str, Any]:
        owner = self._authorise(authenticated_user_id, user_id)
        attempt_no = int(attempt_no)
        max_cost_micros = int(max_cost_micros)
        if attempt_no <= 0 or max_cost_micros < 0 or not provider or not model:
            raise ValueError("valid attempt, provider, model and cost are required")
        now = _utcnow()
        with self._transaction() as conn:
            reservation = self._owned_reservation(conn, owner, reservation_id)
            existing = conn.execute(
                """SELECT * FROM provider_usage
                   WHERE reservation_id = ? AND attempt_no = ?""",
                (reservation_id, attempt_no),
            ).fetchone()
            if existing:
                signature = (
                    existing["provider"],
                    existing["model"],
                    existing["max_cost_micros"],
                    existing["provider_request_id"],
                )
                if signature != (provider, model, max_cost_micros, provider_request_id):
                    raise IdempotencyConflict("provider attempt number was reused")
                return {**dict(existing), "idempotent": True}
            if reservation["status"] not in {"reserved", "running"}:
                raise InvalidLedgerState("provider call cannot start from this state")
            total = conn.execute(
                """SELECT COALESCE(SUM(max_cost_micros), 0) AS total
                   FROM provider_usage WHERE reservation_id = ?""",
                (reservation_id,),
            ).fetchone()["total"]
            if total + max_cost_micros > reservation["provider_budget_micros"]:
                raise InsufficientCredits("provider attempt exceeds reserved financial budget")
            usage_id = str(uuid.uuid4())
            conn.execute(
                """INSERT INTO provider_usage
                   (usage_id, reservation_id, attempt_no, provider, model, state,
                    max_cost_micros, provider_request_id, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, 'started', ?, ?, ?, ?)""",
                (
                    usage_id,
                    reservation_id,
                    attempt_no,
                    provider,
                    model,
                    max_cost_micros,
                    provider_request_id,
                    now,
                    now,
                ),
            )
            conn.execute(
                """UPDATE credit_reservations SET status = 'running', updated_at = ?
                   WHERE reservation_id = ?""",
                (now, reservation_id),
            )
            row = conn.execute(
                "SELECT * FROM provider_usage WHERE usage_id = ?", (usage_id,)
            ).fetchone()
            return {**dict(row), "idempotent": False}

    def settle_provider_attempt(
        self,
        *,
        authenticated_user_id: str,
        user_id: str,
        reservation_id: str,
        attempt_no: int,
        state: str,
        actual_cost_micros: int | None,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
    ) -> dict[str, Any]:
        owner = self._authorise(authenticated_user_id, user_id)
        if state not in {"succeeded", "failed", "uncertain"}:
            raise ValueError("invalid provider attempt state")
        if state in {"succeeded", "failed"} and actual_cost_micros is None:
            raise ValueError("settled provider attempts require an actual cost")
        if actual_cost_micros is not None and int(actual_cost_micros) < 0:
            raise ValueError("actual provider cost cannot be negative")
        now = _utcnow()
        with self._transaction() as conn:
            self._owned_reservation(conn, owner, reservation_id)
            usage = conn.execute(
                """SELECT * FROM provider_usage
                   WHERE reservation_id = ? AND attempt_no = ?""",
                (reservation_id, int(attempt_no)),
            ).fetchone()
            if not usage:
                raise InvalidLedgerState("provider attempt does not exist")
            reconciling_uncertain = (
                usage["state"] == "uncertain"
                and state in {"succeeded", "failed"}
                and actual_cost_micros is not None
            )
            if usage["state"] != "started" and not reconciling_uncertain:
                requested = (
                    state,
                    actual_cost_micros,
                    input_tokens,
                    output_tokens,
                )
                stored = (
                    usage["state"],
                    usage["actual_cost_micros"],
                    usage["input_tokens"],
                    usage["output_tokens"],
                )
                if requested != stored:
                    raise IdempotencyConflict("provider attempt was settled differently")
                return {**dict(usage), "idempotent": True}
            if actual_cost_micros is not None and actual_cost_micros > usage["max_cost_micros"]:
                raise InvalidLedgerState("actual provider cost exceeds its reserved maximum")
            conn.execute(
                """UPDATE provider_usage
                   SET state = ?, actual_cost_micros = ?, input_tokens = ?,
                       output_tokens = ?, updated_at = ? WHERE usage_id = ?""",
                (
                    state,
                    actual_cost_micros,
                    input_tokens,
                    output_tokens,
                    now,
                    usage["usage_id"],
                ),
            )
            row = conn.execute(
                "SELECT * FROM provider_usage WHERE usage_id = ?",
                (usage["usage_id"],),
            ).fetchone()
            return {**dict(row), "idempotent": False}

    @staticmethod
    def _owned_reservation(
        conn: sqlite3.Connection, user_id: str, reservation_id: str
    ) -> sqlite3.Row:
        row = conn.execute(
            """SELECT * FROM credit_reservations
               WHERE reservation_id = ? AND user_id = ?""",
            (reservation_id, user_id),
        ).fetchone()
        if not row:
            raise InvalidLedgerState("reservation does not exist for this user")
        return row

    def release(
        self,
        *,
        authenticated_user_id: str,
        user_id: str,
        reservation_id: str,
    ) -> dict[str, Any]:
        owner = self._authorise(authenticated_user_id, user_id)
        with self._transaction() as conn:
            reservation = self._owned_reservation(conn, owner, reservation_id)
            if reservation["status"] == "released":
                return {**dict(reservation), "idempotent": True}
            if reservation["status"] != "reserved":
                raise InvalidLedgerState("only a never-started reservation can be released")
            attempts = conn.execute(
                "SELECT COUNT(*) AS total FROM provider_usage WHERE reservation_id = ?",
                (reservation_id,),
            ).fetchone()["total"]
            if attempts:
                raise InvalidLedgerState("provider activity prevents a pre-call release")
            now = _utcnow()
            self._finalise(
                conn,
                reservation=reservation,
                capture_credits=0,
                provider_spent_micros=0,
                final_status="released",
                now=now,
            )
            row = self._owned_reservation(conn, owner, reservation_id)
            return {**dict(row), "idempotent": False}

    def capture(
        self,
        *,
        authenticated_user_id: str,
        user_id: str,
        reservation_id: str,
        captured_credits: int | None = None,
        provider_spent_micros: int = 0,
    ) -> dict[str, Any]:
        owner = self._authorise(authenticated_user_id, user_id)
        provider_spent_micros = int(provider_spent_micros)
        with self._transaction() as conn:
            reservation = self._owned_reservation(conn, owner, reservation_id)
            amount = (
                reservation["quoted_credits"]
                if captured_credits is None
                else int(captured_credits)
            )
            if amount < 0 or amount > reservation["quoted_credits"]:
                raise ValueError("captured credits must fit the reservation")
            if provider_spent_micros < 0 or provider_spent_micros > reservation["provider_budget_micros"]:
                raise ValueError("provider spend must fit the reservation")
            if reservation["status"] == "captured":
                if (
                    reservation["captured_credits"] != amount
                    or reservation["provider_spent_micros"] != provider_spent_micros
                ):
                    raise IdempotencyConflict("reservation was captured differently")
                return {**dict(reservation), "idempotent": True}
            if reservation["status"] not in {"reserved", "running", "uncertain"}:
                raise InvalidLedgerState("reservation cannot be captured from this state")
            usages = conn.execute(
                """SELECT state, max_cost_micros, actual_cost_micros
                   FROM provider_usage WHERE reservation_id = ?""",
                (reservation_id,),
            ).fetchall()
            if amount and not usages:
                raise InvalidLedgerState(
                    "credits cannot be captured before a provider attempt"
                )
            if any(usage["state"] in {"started", "uncertain"} for usage in usages):
                raise InvalidLedgerState(
                    "provider usage must be reconciled before capture"
                )
            billable_ceiling = sum(
                usage["actual_cost_micros"] or 0
                for usage in usages
            )
            if provider_spent_micros > billable_ceiling:
                raise InvalidLedgerState(
                    "provider spend exceeds settled provider usage"
                )
            now = _utcnow()
            self._finalise(
                conn,
                reservation=reservation,
                capture_credits=amount,
                provider_spent_micros=provider_spent_micros,
                final_status="captured",
                now=now,
            )
            row = self._owned_reservation(conn, owner, reservation_id)
            return {**dict(row), "idempotent": False}

    def _mark_grant_expired(
        self,
        conn: sqlite3.Connection,
        *,
        grant: sqlite3.Row,
        cutoff: str,
        event_now: str,
        future_cutoff_approval: str | None = None,
    ) -> bool:
        """Persist an authoritative expiration exactly once.

        ``cutoff`` is authoritative rather than inferred later from the wall
        clock.  This also makes an explicitly approved administrative future
        cutoff durable.  Reserved credits are expired when their reservation
        is finalised; only currently available credits are removed here.
        """

        if grant["expired_at"] is not None:
            return False
        if grant["expires_at"] is None or grant["expires_at"] > cutoff:
            return False

        available_expired = grant["remaining_credits"]
        conn.execute(
            """UPDATE credit_grants
               SET remaining_credits = 0, expired_at = ?, expiration_cutoff = ?
               WHERE grant_id = ? AND expired_at IS NULL""",
            (event_now, cutoff, grant["grant_id"]),
        )
        conn.execute(
            """UPDATE credit_accounts
               SET available_credits = available_credits - ?, updated_at = ?
               WHERE user_id = ?""",
            (available_expired, event_now, grant["user_id"]),
        )
        self._event(
            conn,
            user_id=grant["user_id"],
            event_type="expire",
            grant_id=grant["grant_id"],
            delta_available=-available_expired,
            metadata={
                "phase": "grant_expiration",
                "cutoff": cutoff,
                "future_cutoff_approval": future_cutoff_approval,
                "available_expired": available_expired,
                "reserved_at_expiration": grant["reserved_credits"],
            },
            now=event_now,
        )
        return True

    def _finalise(
        self,
        conn: sqlite3.Connection,
        *,
        reservation: sqlite3.Row,
        capture_credits: int,
        provider_spent_micros: int,
        final_status: str,
        now: str,
    ) -> None:
        to_capture = capture_credits
        released_total = 0
        expired_total = 0
        allocations = conn.execute(
            """SELECT allocation.*,
                      grant.user_id AS grant_user_id,
                      grant.remaining_credits AS grant_remaining_credits,
                      grant.reserved_credits AS grant_reserved_credits,
                      grant.expires_at AS grant_expires_at,
                      grant.expired_at AS grant_expired_at,
                      grant.expiration_cutoff AS grant_expiration_cutoff,
                      grant.created_at AS grant_created_at
                 FROM credit_allocations AS allocation
                 JOIN credit_grants AS grant
                   ON grant.grant_id = allocation.grant_id
                WHERE allocation.reservation_id = ?
                ORDER BY CASE WHEN grant.expires_at IS NULL THEN 1 ELSE 0 END,
                         grant.expires_at, grant.created_at, grant.grant_id""",
            (reservation["reservation_id"],),
        ).fetchall()
        for allocation in allocations:
            grant = conn.execute(
                "SELECT * FROM credit_grants WHERE grant_id = ?",
                (allocation["grant_id"],),
            ).fetchone()
            if not grant:
                raise InvalidLedgerState("allocation grant is missing")
            self._mark_grant_expired(
                conn,
                grant=grant,
                cutoff=now,
                event_now=now,
            )
            grant = conn.execute(
                "SELECT * FROM credit_grants WHERE grant_id = ?",
                (allocation["grant_id"],),
            ).fetchone()

            captured = min(to_capture, allocation["reserved_credits"])
            unconsumed = allocation["reserved_credits"] - captured
            expired = unconsumed if grant["expired_at"] is not None else 0
            released = unconsumed - expired
            to_capture -= captured
            released_total += released
            expired_total += expired
            conn.execute(
                """UPDATE credit_allocations
                   SET captured_credits = ?, released_credits = ?,
                       expired_credits = ?
                   WHERE reservation_id = ? AND grant_id = ?""",
                (
                    captured,
                    released,
                    expired,
                    reservation["reservation_id"],
                    allocation["grant_id"],
                ),
            )
            conn.execute(
                """UPDATE credit_grants
                   SET reserved_credits = reserved_credits - ?,
                       remaining_credits = remaining_credits + ?
                   WHERE grant_id = ?""",
                (allocation["reserved_credits"], released, allocation["grant_id"]),
            )
            if expired:
                self._event(
                    conn,
                    user_id=reservation["user_id"],
                    event_type="expire",
                    grant_id=allocation["grant_id"],
                    reservation_id=reservation["reservation_id"],
                    delta_reserved=-expired,
                    metadata={
                        "phase": "reserved_finalisation",
                        "final_status": final_status,
                        "expiration_cutoff": grant["expiration_cutoff"],
                        "reserved_expired": expired,
                    },
                    now=now,
                )
        if to_capture:
            raise InvalidLedgerState("allocation total is lower than capture amount")
        if capture_credits + released_total + expired_total != reservation["quoted_credits"]:
            raise InvalidLedgerState("allocation finalisation does not conserve credits")
        conn.execute(
            """UPDATE credit_accounts
               SET available_credits = available_credits + ?,
                   reserved_credits = reserved_credits - ?,
                   lifetime_captured = lifetime_captured + ?, updated_at = ?
               WHERE user_id = ?""",
            (
                released_total,
                reservation["quoted_credits"],
                capture_credits,
                now,
                reservation["user_id"],
            ),
        )
        conn.execute(
            """UPDATE credit_reservations
               SET captured_credits = ?, provider_spent_micros = ?,
                   uncertain_provider_micros = 0, status = ?, updated_at = ?,
                   finalised_at = ? WHERE reservation_id = ?""",
            (
                capture_credits,
                provider_spent_micros,
                final_status,
                now,
                now,
                reservation["reservation_id"],
            ),
        )
        if capture_credits:
            self._event(
                conn,
                user_id=reservation["user_id"],
                event_type="capture",
                reservation_id=reservation["reservation_id"],
                delta_reserved=-capture_credits,
                delta_consumed=capture_credits,
                provider_micros=provider_spent_micros,
                now=now,
            )
        if final_status == "released" or released_total:
            self._event(
                conn,
                user_id=reservation["user_id"],
                event_type="release",
                reservation_id=reservation["reservation_id"],
                delta_available=released_total,
                delta_reserved=-released_total,
                metadata={
                    "returned_to_available": released_total,
                    "expired_instead_of_released": expired_total,
                },
                now=now,
            )

    def mark_uncertain(
        self,
        *,
        authenticated_user_id: str,
        user_id: str,
        reservation_id: str,
        uncertain_provider_micros: int,
    ) -> dict[str, Any]:
        owner = self._authorise(authenticated_user_id, user_id)
        uncertain_provider_micros = int(uncertain_provider_micros)
        now = _utcnow()
        with self._transaction() as conn:
            reservation = self._owned_reservation(conn, owner, reservation_id)
            if uncertain_provider_micros < 0 or uncertain_provider_micros > reservation["provider_budget_micros"]:
                raise ValueError("uncertain spend must fit the reserved provider budget")
            if reservation["status"] == "uncertain":
                if reservation["uncertain_provider_micros"] != uncertain_provider_micros:
                    raise IdempotencyConflict("uncertain spend was recorded differently")
                return {**dict(reservation), "idempotent": True}
            if reservation["status"] not in {"reserved", "running"}:
                raise InvalidLedgerState("reservation cannot become uncertain")
            conn.execute(
                """UPDATE credit_reservations
                   SET status = 'uncertain', uncertain_provider_micros = ?,
                       updated_at = ? WHERE reservation_id = ?""",
                (uncertain_provider_micros, now, reservation_id),
            )
            self._event(
                conn,
                user_id=owner,
                event_type="uncertain",
                reservation_id=reservation_id,
                provider_micros=uncertain_provider_micros,
                now=now,
            )
            row = self._owned_reservation(conn, owner, reservation_id)
            return {**dict(row), "idempotent": False}

    def expire_grants(
        self,
        *,
        now: datetime | str | None = None,
        future_cutoff_approval: str | None = None,
    ) -> int:
        wall_time = _utcnow()
        cutoff = _normalise_expiry(now) or wall_time
        approval = str(future_cutoff_approval or "").strip() or None
        if cutoff > wall_time and (approval is None or len(approval) > 200):
            raise InvalidLedgerState(
                "future expiration cutoff requires explicit approval"
            )
        expired_count = 0
        with self._transaction() as conn:
            rows = conn.execute(
                """SELECT * FROM credit_grants
                   WHERE expires_at IS NOT NULL AND expires_at <= ?
                     AND expired_at IS NULL
                   ORDER BY user_id, expires_at, grant_id""",
                (cutoff,),
            ).fetchall()
            for grant in rows:
                if self._mark_grant_expired(
                    conn,
                    grant=grant,
                    cutoff=cutoff,
                    event_now=_utcnow(),
                    future_cutoff_approval=approval if cutoff > wall_time else None,
                ):
                    expired_count += 1
        return expired_count

    def get_account(self, user_id: str) -> dict[str, Any] | None:
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT * FROM credit_accounts WHERE user_id = ?", (str(user_id),)
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def get_reservation(self, reservation_id: str) -> dict[str, Any] | None:
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT * FROM credit_reservations WHERE reservation_id = ?",
                (reservation_id,),
            ).fetchone()
            return dict(row) if row else None
        finally:
            conn.close()

    def ledger_events(self, user_id: str) -> list[dict[str, Any]]:
        conn = self._connect()
        try:
            rows = conn.execute(
                """SELECT * FROM credit_ledger_events
                   WHERE user_id = ? ORDER BY sequence_no""",
                (str(user_id),),
            ).fetchall()
            return [dict(row) for row in rows]
        finally:
            conn.close()
