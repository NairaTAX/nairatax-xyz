"""FIFO cost-basis tracking across a user's whole portfolio.

Lots are pooled per asset across every account the caller feeds events from
— not per account. That's what makes self-transfers a pure no-op: a
transfer between two of the user's own wallets never removes the asset from
the portfolio, so there's nothing to dispose of and nothing new to acquire.
Modelling this per-account instead would require tracking which specific lot
crossed which transfer, for no benefit, since tax is owed by the person, not
the wallet.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

from nairatax.models import (
    Asset,
    Classification,
    ClassifiedEvent,
    CostBasisLot,
    Disposal,
    IncomeEvent,
    LotConsumption,
)
from nairatax.pricing import PriceOracle


class InsufficientCostBasisError(RuntimeError):
    """Raised when a disposal is larger than the tracked holdings of that
    asset — i.e. the event stream is missing an earlier acquisition. This
    should surface to the user rather than be silently absorbed, since it
    means the report is built on an incomplete history.
    """


@dataclass
class CostBasisResult:
    disposals: list[Disposal] = field(default_factory=list)
    income_events: list[IncomeEvent] = field(default_factory=list)
    needs_review: list[ClassifiedEvent] = field(default_factory=list)


class FifoCostBasisEngine:
    def __init__(self, price_oracle: PriceOracle) -> None:
        self._price_oracle = price_oracle
        self._lots: dict[str, list[CostBasisLot]] = {}
        self._lot_sequence = 0

    def _next_lot_id(self) -> str:
        self._lot_sequence += 1
        return f"lot-{self._lot_sequence}"

    def acquire(
        self,
        asset: Asset,
        quantity: Decimal,
        unit_cost_fiat: Decimal,
        acquired_at: datetime,
        source_event_id: str,
    ) -> CostBasisLot:
        lot = CostBasisLot(
            lot_id=self._next_lot_id(),
            asset=asset,
            acquired_at=acquired_at,
            original_quantity=quantity,
            remaining_quantity=quantity,
            unit_cost_fiat=unit_cost_fiat,
            source_event_id=source_event_id,
        )
        self._lots.setdefault(asset.id, []).append(lot)
        return lot

    def dispose(
        self,
        asset: Asset,
        quantity: Decimal,
        proceeds_fiat: Decimal,
        disposed_at: datetime,
        event_id: str,
    ) -> Disposal:
        queue = self._lots.setdefault(asset.id, [])
        remaining_to_match = quantity
        consumed: list[LotConsumption] = []
        cost_basis_total = Decimal("0")

        while remaining_to_match > 0:
            if not queue:
                raise InsufficientCostBasisError(
                    f"Not enough tracked lots of {asset.id} to dispose {quantity}; "
                    f"short by {remaining_to_match}. The event history is missing "
                    "an earlier acquisition."
                )
            lot = queue[0]
            take = min(lot.remaining_quantity, remaining_to_match)
            cost_basis_total += take * lot.unit_cost_fiat
            consumed.append(
                LotConsumption(
                    lot_id=lot.lot_id,
                    quantity=take,
                    unit_cost_fiat=lot.unit_cost_fiat,
                    acquired_at=lot.acquired_at,
                )
            )
            remaining_in_lot = lot.remaining_quantity - take
            if remaining_in_lot <= 0:
                queue.pop(0)
            else:
                queue[0] = lot.model_copy(update={"remaining_quantity": remaining_in_lot})
            remaining_to_match -= take

        return Disposal(
            event_id=event_id,
            asset=asset,
            disposed_at=disposed_at,
            quantity=quantity,
            proceeds_fiat=proceeds_fiat,
            cost_basis_fiat=cost_basis_total,
            lots_consumed=consumed,
        )

    def _fmv_and_unit_cost(
        self, asset: Asset, amount: Decimal, at: datetime
    ) -> tuple[Decimal, Decimal]:
        fmv_total = self._price_oracle.fiat_value(asset, amount, at)
        unit_cost = fmv_total / amount if amount != 0 else Decimal("0")
        return fmv_total, unit_cost

    def process(self, classified_events: list[ClassifiedEvent]) -> CostBasisResult:
        """Walk a chronologically ordered stream of classified events,
        updating the lot pool and collecting disposals, income events, and
        anything left NEEDS_REVIEW for the caller to surface.
        """
        result = CostBasisResult()

        for classified in classified_events:
            event = classified.event

            if classified.classification is Classification.DISPOSAL:
                proceeds, _ = self._fmv_and_unit_cost(event.asset, event.amount, event.timestamp)
                disposal = self.dispose(
                    event.asset, event.amount, proceeds, event.timestamp, event.event_id
                )
                result.disposals.append(disposal)

                if event.counter_asset is not None and event.counter_amount:
                    # Cost basis carries the disposal's proceeds forward as the
                    # newly acquired asset's cost — no gain/loss "in kind" at
                    # the swap boundary beyond what was already realised above.
                    unit_cost = proceeds / event.counter_amount
                    self.acquire(
                        event.counter_asset,
                        event.counter_amount,
                        unit_cost,
                        event.timestamp,
                        event.event_id,
                    )

            elif classified.classification is Classification.INCOME:
                fmv_total, unit_cost = self._fmv_and_unit_cost(
                    event.asset, event.amount, event.timestamp
                )
                self.acquire(event.asset, event.amount, unit_cost, event.timestamp, event.event_id)
                result.income_events.append(
                    IncomeEvent(
                        event_id=event.event_id,
                        asset=event.asset,
                        received_at=event.timestamp,
                        quantity=event.amount,
                        fair_market_value_fiat=fmv_total,
                    )
                )

            elif classified.classification in (Classification.ACQUISITION, Classification.GIFT):
                _, unit_cost = self._fmv_and_unit_cost(event.asset, event.amount, event.timestamp)
                self.acquire(event.asset, event.amount, unit_cost, event.timestamp, event.event_id)

            elif classified.classification is Classification.SELF_TRANSFER:
                continue  # no cost-basis effect — see module docstring

            elif classified.classification is Classification.NEEDS_REVIEW:
                result.needs_review.append(classified)

        return result
