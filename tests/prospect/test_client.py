import pytest

from gabriel_prospect.client import init_prospect_storage
from gabriel_prospect.repository import get_repository, init_repository


@pytest.fixture(autouse=True)
def reset_global_repository():
    yield
    init_repository(None)


def test_missing_prospect_configuration_disables_storage_without_factory_call(monkeypatch, tmp_path):
    monkeypatch.delenv("GABRIEL_PROSPECT_SUPABASE_URL", raising=False)
    monkeypatch.delenv("GABRIEL_PROSPECT_SUPABASE_SECRET_KEY", raising=False)
    monkeypatch.setenv("SUPABASE_URL", "https://legacy.example.test")
    monkeypatch.setenv("SUPABASE_KEY", "legacy-secret-must-not-be-used")
    calls = []

    configured = init_prospect_storage(
        client_factory=lambda *_args, **_kwargs: calls.append(True),
        config_path=tmp_path / "missing.env",
    )

    assert configured is False
    assert calls == []
    assert get_repository().client is None


def test_partial_prospect_configuration_fails_closed(monkeypatch, tmp_path):
    monkeypatch.setenv("GABRIEL_PROSPECT_SUPABASE_URL", "https://prospect.example.test")
    monkeypatch.delenv("GABRIEL_PROSPECT_SUPABASE_SECRET_KEY", raising=False)

    assert init_prospect_storage(
        client_factory=lambda *_args, **_kwargs: object(),
        config_path=tmp_path / "missing.env",
    ) is False
    assert get_repository().client is None


def test_dedicated_configuration_initializes_only_the_prospect_repository(monkeypatch):
    monkeypatch.setenv("GABRIEL_PROSPECT_SUPABASE_URL", "https://prospect.example.test")
    monkeypatch.setenv("GABRIEL_PROSPECT_SUPABASE_SECRET_KEY", "dedicated-test-secret")
    sentinel = object()
    received = []

    def factory(url, key):
        received.append((url, key))
        return sentinel

    assert init_prospect_storage(client_factory=factory) is True
    assert received == [("https://prospect.example.test", "dedicated-test-secret")]
    assert get_repository().client is sentinel


def test_client_initialization_failure_never_logs_the_secret(monkeypatch, caplog):
    secret = "dedicated-secret-that-must-not-leak"
    monkeypatch.setenv("GABRIEL_PROSPECT_SUPABASE_URL", "https://prospect.example.test")
    monkeypatch.setenv("GABRIEL_PROSPECT_SUPABASE_SECRET_KEY", secret)

    def broken_factory(_url, _key):
        raise RuntimeError(f"connection rejected for {secret}")

    assert init_prospect_storage(client_factory=broken_factory) is False
    assert get_repository().client is None
    assert secret not in caplog.text


def test_dedicated_local_file_configures_prospect_storage(monkeypatch, tmp_path):
    config_path = tmp_path / ".env.prospect.local"
    config_path.write_text(
        "GABRIEL_PROSPECT_SUPABASE_URL=https://prospect-dev.example.test\n"
        "GABRIEL_PROSPECT_SUPABASE_SECRET_KEY=sb_secret_test-only\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("GABRIEL_PROSPECT_SUPABASE_URL", raising=False)
    monkeypatch.delenv("GABRIEL_PROSPECT_SUPABASE_SECRET_KEY", raising=False)
    received = []

    assert init_prospect_storage(
        client_factory=lambda url, key: received.append((url, key)) or object(),
        config_path=config_path,
    ) is True
    assert received == [(
        "https://prospect-dev.example.test",
        "sb_secret_test-only",
    )]


def test_process_environment_takes_precedence_over_local_file(monkeypatch, tmp_path):
    config_path = tmp_path / ".env.prospect.local"
    config_path.write_text(
        "GABRIEL_PROSPECT_SUPABASE_URL=https://file.example.test\n"
        "GABRIEL_PROSPECT_SUPABASE_SECRET_KEY=sb_secret_from-file\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("GABRIEL_PROSPECT_SUPABASE_URL", "https://environment.example.test")
    monkeypatch.setenv("GABRIEL_PROSPECT_SUPABASE_SECRET_KEY", "sb_secret_from-environment")
    received = []

    assert init_prospect_storage(
        client_factory=lambda url, key: received.append((url, key)) or object(),
        config_path=config_path,
    ) is True
    assert received == [(
        "https://environment.example.test",
        "sb_secret_from-environment",
    )]


def test_local_file_never_loads_legacy_supabase_variables(monkeypatch, tmp_path):
    config_path = tmp_path / ".env.prospect.local"
    config_path.write_text(
        "SUPABASE_URL=https://legacy.example.test\n"
        "SUPABASE_KEY=legacy-secret-must-not-be-used\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("GABRIEL_PROSPECT_SUPABASE_URL", raising=False)
    monkeypatch.delenv("GABRIEL_PROSPECT_SUPABASE_SECRET_KEY", raising=False)
    calls = []

    assert init_prospect_storage(
        client_factory=lambda *_args: calls.append(True),
        config_path=config_path,
    ) is False
    assert calls == []
    assert get_repository().client is None
