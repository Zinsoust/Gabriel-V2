"""Central, fail-closed authorization for Gabriel administrators.

Email addresses are never treated as proof of privilege. Administrators are
selected only by the stable internal ``user_id`` stored in an authenticated
session.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Mapping


def configured_admin_user_ids(env=None) -> frozenset[str]:
    """Return configured admin UUIDs, or no admins for an invalid setting.

    A single malformed entry invalidates the complete setting. This prevents a
    typo from silently producing a privilege set different from the operator's
    intent.
    """
    env = os.environ if env is None else env
    raw = str(env.get("ADMIN_USER_IDS", "") or "").strip()
    if not raw:
        return frozenset()

    parsed: set[str] = set()
    for value in raw.split(","):
        candidate = value.strip()
        if not candidate:
            return frozenset()
        try:
            parsed.add(str(uuid.UUID(candidate)))
        except (ValueError, TypeError, AttributeError):
            return frozenset()
    return frozenset(parsed)


def is_admin_user_id(user_id, env=None) -> bool:
    """Return true only for an explicitly configured internal UUID."""
    if not user_id:
        return False
    try:
        normalized = str(uuid.UUID(str(user_id).strip()))
    except (ValueError, TypeError, AttributeError):
        return False
    return normalized in configured_admin_user_ids(env)


def is_admin_user(user, env=None) -> bool:
    """Check an authenticated identity without ever consulting its email."""
    if not isinstance(user, Mapping):
        return False
    return is_admin_user_id(user.get("user_id"), env=env)
