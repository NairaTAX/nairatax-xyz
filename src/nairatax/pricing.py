"""Fair-market-value pricing seam.

The cost basis and rules engines need to convert an asset quantity at a point
in time into the reporting currency, but historical multi-asset fiat pricing
is a data-provider integration NairaTax hasn't built yet (see the Roadmap in
the README). :class:`PriceOracle` is the interface that integration will
implement; :class:`StaticPriceOracle` is a fixed-rate stand-in so the rest of
the pipeline can be built and tested end-to-end today, without waiting on
that integration.

Do not use ``StaticPriceOracle`` against real account activity — it applies
one rate regardless of date, which will misstate gains/losses for anything
that didn't happen on the day its rate was quoted.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Protocol

from nairatax.models import Asset


class PriceUnavailableError(LookupError):
    """Raised when an oracle has no rate for the requested asset."""


class PriceOracle(Protocol):
    def fiat_value(self, asset: Asset, amount: Decimal, at: datetime) -> Decimal:
        """Return the fair market value of ``amount`` of ``asset`` at ``at``,
        in the reporting currency. Raises :class:`PriceUnavailableError` if
        no rate can be determined.
        """
        ...


class StaticPriceOracle:
    """Fixed per-asset rate, ignoring ``at`` entirely.

    Intended for tests, demos, and development — not for producing a report
    anyone files on.
    """

    def __init__(self, rates: dict[str, Decimal]) -> None:
        self._rates = dict(rates)

    def fiat_value(self, asset: Asset, amount: Decimal, at: datetime) -> Decimal:
        del at  # deliberately ignored — see class docstring
        try:
            rate = self._rates[asset.id]
        except KeyError as exc:
            raise PriceUnavailableError(f"no static rate configured for {asset.id}") from exc
        return amount * rate
