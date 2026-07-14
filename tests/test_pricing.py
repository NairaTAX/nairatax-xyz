from datetime import UTC, datetime
from decimal import Decimal

import pytest

from nairatax.models import Asset
from nairatax.pricing import PriceUnavailableError, StaticPriceOracle

NOW = datetime(2026, 1, 1, tzinfo=UTC)


def test_fiat_value_multiplies_amount_by_configured_rate():
    oracle = StaticPriceOracle({"native": Decimal("1500")})
    assert oracle.fiat_value(Asset(), Decimal("2"), NOW) == Decimal("3000")


def test_unconfigured_asset_raises_price_unavailable():
    oracle = StaticPriceOracle({})
    with pytest.raises(PriceUnavailableError):
        oracle.fiat_value(Asset(), Decimal("1"), NOW)


def test_rate_is_independent_of_timestamp():
    oracle = StaticPriceOracle({"native": Decimal("1500")})
    earlier = oracle.fiat_value(Asset(), Decimal("1"), datetime(2020, 1, 1, tzinfo=UTC))
    later = oracle.fiat_value(Asset(), Decimal("1"), datetime(2030, 1, 1, tzinfo=UTC))
    assert earlier == later == Decimal("1500")
