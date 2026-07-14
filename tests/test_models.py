from datetime import UTC, datetime
from decimal import Decimal

from nairatax.models import (
    Asset,
    Classification,
    ClassifiedEvent,
    Disposal,
    EventKind,
    LotConsumption,
    NormalizedEvent,
    TaxLineItem,
    TaxLineItemCategory,
    TaxReport,
)

USDC_ISSUER = "GA5ZSEJYB37JRC5AVCIA5MOP4RHTM335X2KGX3IHOJAPP5RE34K4KZVN"


def test_native_asset_id_ignores_issuer():
    assert Asset().id == "native"
    assert Asset(code="native", issuer="anything").id == "native"


def test_issued_asset_id_includes_issuer():
    asset = Asset(code="USDC", issuer=USDC_ISSUER)
    assert asset.id == f"USDC:{USDC_ISSUER}"


def test_two_assets_same_code_different_issuer_are_distinct():
    a = Asset(code="USDC", issuer=USDC_ISSUER)
    b = Asset(code="USDC", issuer="GDIFFERENT")
    assert a.id != a.id[::-1]  # sanity
    assert a.id != b.id


def _event(**overrides) -> NormalizedEvent:
    defaults = dict(
        event_id="op-1",
        account="GACCOUNT",
        timestamp=datetime(2026, 3, 1, tzinfo=UTC),
        kind=EventKind.PAYMENT_IN,
        asset=Asset(),
        amount=Decimal("10"),
        source_operation_id="op-1",
    )
    defaults.update(overrides)
    return NormalizedEvent(**defaults)


def test_classified_event_wraps_normalized_event():
    event = _event()
    classified = ClassifiedEvent(
        event=event, classification=Classification.INCOME, reason="unsolicited inflow"
    )
    assert classified.event.event_id == "op-1"
    assert classified.classification is Classification.INCOME


def test_disposal_gain_loss_is_proceeds_minus_cost_basis():
    disposal = Disposal(
        event_id="op-2",
        asset=Asset(),
        disposed_at=datetime(2026, 4, 1, tzinfo=UTC),
        quantity=Decimal("5"),
        proceeds_fiat=Decimal("500000"),
        cost_basis_fiat=Decimal("300000"),
        lots_consumed=[
            LotConsumption(
                lot_id="lot-1",
                quantity=Decimal("5"),
                unit_cost_fiat=Decimal("60000"),
                acquired_at=datetime(2026, 1, 1, tzinfo=UTC),
            )
        ],
    )
    assert disposal.gain_loss_fiat == Decimal("200000")


def test_disposal_gain_loss_can_be_negative():
    disposal = Disposal(
        event_id="op-3",
        asset=Asset(),
        disposed_at=datetime(2026, 4, 1, tzinfo=UTC),
        quantity=Decimal("1"),
        proceeds_fiat=Decimal("100"),
        cost_basis_fiat=Decimal("150"),
        lots_consumed=[],
    )
    assert disposal.gain_loss_fiat == Decimal("-50")


def test_tax_report_aggregates_by_category():
    report = TaxReport(
        account="GACCOUNT",
        jurisdiction="nigeria",
        currency="NGN",
        period_start=datetime(2026, 1, 1, tzinfo=UTC),
        period_end=datetime(2026, 12, 31, tzinfo=UTC),
        line_items=[
            TaxLineItem(
                event_id="op-1",
                date=datetime(2026, 2, 1, tzinfo=UTC),
                category=TaxLineItemCategory.CAPITAL_GAIN,
                asset=Asset(),
                quantity=Decimal("1"),
                amount_fiat=Decimal("1000"),
                tax_owed_fiat=Decimal("150"),
                description="disposal",
            ),
            TaxLineItem(
                event_id="op-2",
                date=datetime(2026, 3, 1, tzinfo=UTC),
                category=TaxLineItemCategory.INCOME,
                asset=Asset(),
                quantity=Decimal("2"),
                amount_fiat=Decimal("2000"),
                tax_owed_fiat=Decimal("400"),
                description="income",
            ),
        ],
    )
    assert report.total_capital_gains == Decimal("1000")
    assert report.total_income == Decimal("2000")
    assert report.total_tax_owed == Decimal("550")


def test_tax_report_totals_are_zero_with_no_line_items():
    report = TaxReport(
        account="GACCOUNT",
        jurisdiction="nigeria",
        currency="NGN",
        period_start=datetime(2026, 1, 1, tzinfo=UTC),
        period_end=datetime(2026, 12, 31, tzinfo=UTC),
    )
    assert report.total_capital_gains == Decimal("0")
    assert report.total_income == Decimal("0")
    assert report.total_tax_owed == Decimal("0")
