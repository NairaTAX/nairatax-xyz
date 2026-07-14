"""Environment-driven configuration.

Nothing in this module talks to the network or the filesystem beyond reading
env vars — it exists so every other module takes a ``Settings`` instance
instead of reaching into ``os.environ`` directly, which keeps tests
hermetic and makes the effective config easy to print/debug.
"""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

HORIZON_TESTNET_URL = "https://horizon-testnet.stellar.org"
HORIZON_MAINNET_URL = "https://horizon.stellar.org"
TESTNET_PASSPHRASE = "Test SDF Network ; September 2015"
PUBLIC_NETWORK_PASSPHRASE = "Public Global Stellar Network ; September 2015"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="NAIRATAX_", env_file=".env", extra="ignore")

    horizon_url: str = HORIZON_TESTNET_URL
    network_passphrase: str = TESTNET_PASSPHRASE

    reporting_currency: str = "NGN"
    """ISO 4217 code the final report is denominated in."""

    jurisdiction: str = "nigeria"
    """Which rule pack under ``nairatax/rules/packs`` to apply by default."""

    data_dir: str = "./data"
    """Where cached Horizon pages, price data, and generated reports are written."""

    horizon_page_limit: int = Field(default=200, ge=1, le=200)
    """Records per Horizon page request; 200 is Horizon's own max."""

    horizon_request_timeout_seconds: float = Field(default=30.0, gt=0)


def get_settings() -> Settings:
    """Construct settings from the environment.

    A plain function rather than a module-level singleton — tests and the
    CLI both want to control exactly when env vars are read.
    """
    return Settings()
