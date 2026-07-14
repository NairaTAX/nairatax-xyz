from nairatax.config import HORIZON_TESTNET_URL, TESTNET_PASSPHRASE, get_settings


def test_defaults_point_at_testnet():
    settings = get_settings()
    assert settings.horizon_url == HORIZON_TESTNET_URL
    assert settings.network_passphrase == TESTNET_PASSPHRASE
    assert settings.reporting_currency == "NGN"
    assert settings.jurisdiction == "nigeria"


def test_env_vars_override_defaults(monkeypatch):
    monkeypatch.setenv("NAIRATAX_HORIZON_URL", "https://horizon.stellar.org")
    monkeypatch.setenv("NAIRATAX_JURISDICTION", "ghana")
    settings = get_settings()
    assert settings.horizon_url == "https://horizon.stellar.org"
    assert settings.jurisdiction == "ghana"


def test_horizon_page_limit_is_bounded_by_horizon_api():
    import pytest
    from pydantic import ValidationError

    from nairatax.config import Settings

    with pytest.raises(ValidationError):
        Settings(horizon_page_limit=500)
