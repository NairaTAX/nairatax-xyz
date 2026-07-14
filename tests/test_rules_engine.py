from datetime import UTC, datetime
from decimal import Decimal

from nairatax.models import Asset, Disposal, IncomeEvent
from nairatax.rules.engine import build_tax_line_items, compute_tax
from nairatax.rules.schema import ConsolidatedRelief, RulePack, TaxBand

XLM = Asset()
T0 = datetime(2026, 1, 1, tzinfo=UTC)

NO_RELIEF = ConsolidatedRelief(
    flat_amount=Decimal("0"),
    minimum_percent_of_gross=Decimal("0"),
    additional_percent_of_gross=Decimal("0"),
)

SIMPLE_PACK = RulePack(
    id="test-simple",
    jurisdiction="testland",
    display_name="Testland",
    currency="TST",
    version="0.1.0",
    verified=False,
    source_note="fixture",
    income_tax_bands=[
        TaxBand(upper_bound=Decimal("1000"), rate=Decimal("0.10")),
        TaxBand(upper_bound=None, rate=Decimal("0.20")),
    ],
    consolidated_relief=NO_RELIEF,
)

WITH_RELIEF_PACK = SIMPLE_PACK.model_copy(
    update={
        "consolidated_relief": ConsolidatedRelief(
            flat_amount=Decimal("100"),
            minimum_percent_of_gross=Decimal("0"),
            additional_percent_of_gross=Decimal("0"),
        )
    }
)


def test_zero_or_negative_income_owes_no_tax():
    assert compute_tax(SIMPLE_PACK, Decimal("0")) == Decimal("0")
    assert compute_tax(SIMPLE_PACK, Decimal("-50")) == Decimal("0")


def test_income_within_first_band():
    assert compute_tax(SIMPLE_PACK, Decimal("500")) == Decimal("50")


def test_income_spanning_two_bands():
    # 1000 @ 10% + 500 @ 20% = 100 + 100 = 200
    assert compute_tax(SIMPLE_PACK, Decimal("1500")) == Decimal("200")


def test_relief_is_deducted_before_bands_apply():
    # relief = 100 (flat), taxable = 600 - 100 = 500 -> 500 * 10% = 50
    assert compute_tax(WITH_RELIEF_PACK, Decimal("600")) == Decimal("50")


def _disposal(event_id: str, gain_loss: str) -> Disposal:
    quantity = Decimal("1")
    # proceeds/cost_basis chosen so proceeds - cost_basis == gain_loss
    gain = Decimal(gain_loss)
    return Disposal(
        event_id=event_id,
        asset=XLM,
        disposed_at=T0,
        quantity=quantity,
        proceeds_fiat=max(gain, Decimal("0")) + Decimal("1000"),
        cost_basis_fiat=Decimal("1000") - min(gain, Decimal("0")),
        lots_consumed=[],
    )


def test_build_tax_line_items_allocates_total_tax_exactly():
    disposals = [_disposal("gain-1", "1000"), _disposal("loss-1", "-200")]
    income_events = [
        IncomeEvent(
            event_id="income-1",
            asset=XLM,
            received_at=T0,
            quantity=Decimal("1"),
            fair_market_value_fiat=Decimal("200"),
        )
    ]

    items = build_tax_line_items(SIMPLE_PACK, disposals, income_events)

    by_event = {item.event_id: item for item in items}
    assert by_event["gain-1"].amount_fiat == Decimal("1000")
    assert by_event["loss-1"].amount_fiat == Decimal("-200")
    assert by_event["loss-1"].tax_owed_fiat == Decimal("0")  # losses never owe tax

    # chargeable = net_capital_gain(800) + income(200) = 1000 -> total_tax = 100
    total_tax = compute_tax(SIMPLE_PACK, Decimal("1000"))
    assert total_tax == Decimal("100")
    assert sum((item.tax_owed_fiat for item in items), Decimal("0")) == total_tax

    # capital gains pool = 100 * 800/1000 = 80, all allocated to the one gain line
    assert by_event["gain-1"].tax_owed_fiat == Decimal("80")
    # income pool = 100 * 200/1000 = 20
    assert by_event["income-1"].tax_owed_fiat == Decimal("20")


def test_build_tax_line_items_with_no_activity_is_empty():
    assert build_tax_line_items(SIMPLE_PACK, [], []) == []


def test_build_tax_line_items_all_losses_owe_no_tax():
    disposals = [_disposal("loss-1", "-100"), _disposal("loss-2", "-50")]
    items = build_tax_line_items(SIMPLE_PACK, disposals, [])
    assert all(item.tax_owed_fiat == Decimal("0") for item in items)
