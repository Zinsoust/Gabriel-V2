"""Server-only Supabase client initialization for Gabriel Prospect."""

import logging
import os
from pathlib import Path

from dotenv import dotenv_values

from .repository import init_repository


_logger = logging.getLogger(__name__)
_PROSPECT_CONFIG_PATH = Path(__file__).resolve().parents[1] / ".env.prospect.local"
_PROSPECT_URL_ENV = "GABRIEL_PROSPECT_SUPABASE_URL"
_PROSPECT_SECRET_ENV = "GABRIEL_PROSPECT_SUPABASE_SECRET_KEY"


def _create_client(url, secret_key):
    from supabase import ClientOptions, create_client

    return create_client(
        url,
        secret_key,
        options=ClientOptions(postgrest_client_timeout=30),
    )


def _settings(config_path=None):
    """Read only Prospect settings, with process variables taking precedence."""
    local_values = dotenv_values(config_path or _PROSPECT_CONFIG_PATH)
    url = os.environ.get(_PROSPECT_URL_ENV, local_values.get(_PROSPECT_URL_ENV, ""))
    secret_key = os.environ.get(
        _PROSPECT_SECRET_ENV,
        local_values.get(_PROSPECT_SECRET_ENV, ""),
    )
    return str(url or "").strip(), str(secret_key or "").strip()


def init_prospect_storage(client_factory=None, config_path=None):
    """Configure Prospect storage without ever falling back to Gabriel's client."""
    url, secret_key = _settings(config_path)
    if not url or not secret_key:
        init_repository(None)
        return False

    try:
        client = (client_factory or _create_client)(url, secret_key)
    except Exception as exc:
        init_repository(None)
        _logger.warning(
            "Gabriel Prospect storage initialization failed (%s)",
            type(exc).__name__,
        )
        return False

    init_repository(client)
    return True
