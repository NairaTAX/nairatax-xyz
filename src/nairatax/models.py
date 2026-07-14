"""Core data models shared across ingestion, classification, cost basis, and reporting.

All monetary and quantity fields use ``Decimal`` rather than ``float`` — this is a
tax engine, and binary floating point cannot represent amounts like 0.1 exactly,
which is unacceptable when the output is a number someone reports to a tax
authority.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field

NATIVE_ASSET = "native"
"""Sentinel asset id for XLM, mirroring Horizon's own convention."""


class Asset(BaseModel):
    """A Stellar asset. Native XLM has no issuer; issued assets are identified
    by the (code, issuer) pair, since two assets can share a code on different
    issuing accounts.
    """

    model_config = ConfigDict(frozen=True)

    code: str = NATIVE_ASSET
    issuer: str | None = None

    @property
    def id(self) -> str:
        """Stable string identity for this asset, suitable as a dict key."""
        if self.code == NATIVE_ASSET or self.issuer is None:
            return NATIVE_ASSET
        return f"{self.code}:{self.issuer}"

    def __str__(self) -> str:  # pragma: no cover - trivial
        return self.id


class EventKind(StrEnum):
    """The raw operation shape observed on-chain, before tax classification."""

    PAYMENT_IN = "payment_in"
    PAYMENT_OUT = "payment_out"
    TRADE = "trade"
    PATH_PAYMENT_IN = "path_payment_in"
    PATH_PAYMENT_OUT = "path_payment_out"
    CLAIMABLE_BALANCE_CREATE = "claimable_balance_create"
    CLAIMABLE_BALANCE_CLAIM = "claimable_balance_claim"


class NormalizedEvent(BaseModel):
    """A single economic movement for one account, normalised from whatever
    Horizon operation(s) produced it. This is the unit that classification,
    cost basis, and reporting all operate on.
    """

    model_config = ConfigDict(frozen=True)

    event_id: str
    """Stable id derived from the source operation id (and asset, for trades
    that move two assets in one operation)."""
    account: str
    timestamp: datetime
    kind: EventKind
    asset: Asset
    amount: Decimal
    """Always positive; direction is carried by ``kind``."""
    counter_asset: Asset | None = None
    counter_amount: Decimal | None = None
    """Populated for trades and path payments — the other leg of the swap."""
    counterparty: str | None = None
    """The other account involved, when known (payment sender/receiver)."""
    source_operation_id: str
    memo: str | None = None


class Classification(StrEnum):
    DISPOSAL = "disposal"
    """A taxable disposal of an asset already held (sale, swap, spend)."""
    ACQUISITION = "acquisition"
    """A non-taxable acquisition that establishes cost basis (buy, swap-in)."""
    INCOME = "income"
    """Taxable income at fair market value on receipt (e.g. unsolicited inflow
    treated as income rather than a gift)."""
    SELF_TRANSFER = "self_transfer"
    """Movement between the user's own accounts — not a disposal or income."""
    GIFT = "gift"
    """Received without consideration and not treated as income under the
    active rule pack."""
    NEEDS_REVIEW = "needs_review"
    """The classifier could not confidently assign a category; a human must
    resolve it before the event can be reported."""


class ClassifiedEvent(BaseModel):
    """A :class:`NormalizedEvent` plus the classifier's verdict."""

    model_config = ConfigDict(frozen=True)

    event: NormalizedEvent
    classification: Classification
    reason: str
    """Short human-readable explanation, surfaced in the review UI/report."""


class CostBasisLot(BaseModel):
    """A quantity of an asset acquired at a point in time, tracked so later
    disposals can be matched against it under FIFO.
    """

    model_config = ConfigDict(frozen=True)

    lot_id: str
    asset: Asset
    acquired_at: datetime
    original_quantity: Decimal
    remaining_quantity: Decimal
    unit_cost_fiat: Decimal
    """Fair market value per unit at acquisition, in the reporting currency."""
    source_event_id: str


class LotConsumption(BaseModel):
    """The portion of one lot consumed by a single disposal."""

    model_config = ConfigDict(frozen=True)

    lot_id: str
    quantity: Decimal
    unit_cost_fiat: Decimal
    acquired_at: datetime


class Disposal(BaseModel):
    """A taxable disposal: the proceeds from a :class:`ClassifiedEvent` matched
    against one or more :class:`CostBasisLot` records via FIFO.
    """

    model_config = ConfigDict(frozen=True)

    event_id: str
    asset: Asset
    disposed_at: datetime
    quantity: Decimal
    proceeds_fiat: Decimal
    cost_basis_fiat: Decimal
    lots_consumed: list[LotConsumption]

    @property
    def gain_loss_fiat(self) -> Decimal:
        return self.proceeds_fiat - self.cost_basis_fiat

    @property
    def is_long_term(self) -> bool | None:
        """``None`` when the pack has no long/short distinction; otherwise
        left to the rules engine to set via holding period, since "long term"
        is a jurisdiction-specific threshold, not a universal concept.
        """
        return None


class IncomeEvent(BaseModel):
    """A taxable income event, valued at fair market value on receipt."""

    model_config = ConfigDict(frozen=True)

    event_id: str
    asset: Asset
    received_at: datetime
    quantity: Decimal
    fair_market_value_fiat: Decimal


class TaxLineItemCategory(StrEnum):
    CAPITAL_GAIN = "capital_gain"
    INCOME = "income"


class TaxLineItem(BaseModel):
    """One row of the per-event ledger presented to the user."""

    model_config = ConfigDict(frozen=True)

    event_id: str
    date: datetime
    category: TaxLineItemCategory
    asset: Asset
    quantity: Decimal
    amount_fiat: Decimal
    """Gain/loss for capital_gain rows; fair market value for income rows."""
    tax_owed_fiat: Decimal
    description: str


class TaxReport(BaseModel):
    """The final output: a per-event ledger plus the jurisdiction-computed
    summary of tax owed for the period.
    """

    account: str
    jurisdiction: str
    currency: str
    period_start: datetime
    period_end: datetime
    line_items: list[TaxLineItem] = Field(default_factory=list)
    needs_review_count: int = 0

    @property
    def total_capital_gains(self) -> Decimal:
        return sum(
            (
                li.amount_fiat
                for li in self.line_items
                if li.category == TaxLineItemCategory.CAPITAL_GAIN
            ),
            Decimal("0"),
        )

    @property
    def total_income(self) -> Decimal:
        return sum(
            (li.amount_fiat for li in self.line_items if li.category == TaxLineItemCategory.INCOME),
            Decimal("0"),
        )

    @property
    def total_tax_owed(self) -> Decimal:
        return sum((li.tax_owed_fiat for li in self.line_items), Decimal("0"))
