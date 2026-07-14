from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from nairatax.cost_basis.fifo import FifoCostBasisEngine, InsufficientCostBasisError
from nairatax.models import Asset, Classification, ClassifiedEvent, EventKind, NormalizedEvent
from nairatax.pricing import StaticPriceOracle

XLM = Asset()
USDC = Asset(code="USDC", issuer="GISSUERXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX")
T0 = datetime(2026, 1, 1, tzinfo=UTC)


def _oracle(**rates: str) -> StaticPriceOracle:
    return StaticPriceOracle({asset_id: Decimal(rate) for asset_id, rate in rates.items()})


def _event(**overrides) -> NormalizedEvent:
    defaults = dict(
        event_id="e1",
        account="GACCOUNT",
        timestamp=T0,
        kind=EventKind.PAYMENT_IN,
        asset=XLM,
        amount=Decimal("10"),
        source_operation_id="op-1",
    )
    defaults.update(overrides)
    return NormalizedEvent(**defaults)


def _classified(event, classification) -> ClassifiedEvent:
    return ClassifiedEvent(event=event, classification=classification, reason="test")


# --- acquire/dispose primitives -------------------------------------------------


def test_dispose_from_single_lot_computes_gain():
    engine = FifoCostBasisEngine(_oracle())
    engine.acquire(XLM, Decimal("100"), Decimal("1000"), T0, "acq-1")

    disposal = engine.dispose(
        XLM, Decimal("40"), Decimal("60000"), T0 + timedelta(days=1), "dis-1"
    )

    assert disposal.cost_basis_fiat == Decimal("40000")
    assert disposal.gain_loss_fiat == Decimal("20000")
    assert len(disposal.lots_consumed) == 1
    assert disposal.lots_consumed[0].quantity == Decimal("40")


def test_dispose_across_two_lots_uses_fifo_order():
    engine = FifoCostBasisEngine(_oracle())
    engine.acquire(XLM, Decimal("10"), Decimal("1000"), T0, "acq-1")
    engine.acquire(XLM, Decimal("10"), Decimal("2000"), T0 + timedelta(days=1), "acq-2")

    disposal = engine.dispose(
        XLM, Decimal("15"), Decimal("45000"), T0 + timedelta(days=2), "dis-1"
    )

    # 10 units @1000 + 5 units @2000 = 10000 + 10000 = 20000
    assert disposal.cost_basis_fiat == Decimal("20000")
    assert [lc.lot_id for lc in disposal.lots_consumed] == ["lot-1", "lot-2"]
    assert disposal.lots_consumed[1].quantity == Decimal("5")


def test_partial_lot_consumption_leaves_remainder_for_next_disposal():
    engine = FifoCostBasisEngine(_oracle())
    engine.acquire(XLM, Decimal("10"), Decimal("1000"), T0, "acq-1")

    first = engine.dispose(XLM, Decimal("4"), Decimal("8000"), T0, "dis-1")
    second = engine.dispose(XLM, Decimal("6"), Decimal("12000"), T0, "dis-2")

    assert first.cost_basis_fiat == Decimal("4000")
    assert second.cost_basis_fiat == Decimal("6000")


def test_disposing_more_than_held_raises():
    engine = FifoCostBasisEngine(_oracle())
    engine.acquire(XLM, Decimal("5"), Decimal("1000"), T0, "acq-1")

    with pytest.raises(InsufficientCostBasisError):
        engine.dispose(XLM, Decimal("6"), Decimal("6000"), T0, "dis-1")


# --- process() over classified event streams ------------------------------------


def test_process_income_opens_a_lot_and_records_income():
    engine = FifoCostBasisEngine(_oracle(native="1500"))
    event = _event(kind=EventKind.PAYMENT_IN, amount=Decimal("10"))

    result = engine.process([_classified(event, Classification.INCOME)])

    assert len(result.income_events) == 1
    assert result.income_events[0].fair_market_value_fiat == Decimal("15000")
    # the new lot should be usable for a later disposal at the same cost
    disposal = engine.dispose(XLM, Decimal("10"), Decimal("20000"), T0, "dis-1")
    assert disposal.cost_basis_fiat == Decimal("15000")


def test_process_self_transfer_is_a_no_op():
    engine = FifoCostBasisEngine(_oracle())
    event = _event(kind=EventKind.PAYMENT_OUT, amount=Decimal("999999"))

    result = engine.process([_classified(event, Classification.SELF_TRANSFER)])

    assert result.disposals == []
    assert result.income_events == []
    # no lots were touched, so this does not raise despite the huge amount
    # above never having been acquired
    assert engine._lots == {}


def test_process_needs_review_is_collected_untouched():
    engine = FifoCostBasisEngine(_oracle())
    event = _event(kind=EventKind.PAYMENT_IN)
    classified = _classified(event, Classification.NEEDS_REVIEW)

    result = engine.process([classified])

    assert result.needs_review == [classified]
    assert result.disposals == []


def test_process_disposal_swap_disposes_given_asset_and_opens_counter_lot():
    engine = FifoCostBasisEngine(_oracle(native="1500"))
    engine.acquire(XLM, Decimal("100"), Decimal("1000"), T0, "acq-1")

    swap_event = _event(
        kind=EventKind.TRADE,
        asset=XLM,
        amount=Decimal("100"),
        counter_asset=USDC,
        counter_amount=Decimal("95"),
        timestamp=T0 + timedelta(days=1),
    )
    result = engine.process([_classified(swap_event, Classification.DISPOSAL)])

    assert len(result.disposals) == 1
    disposal = result.disposals[0]
    assert disposal.cost_basis_fiat == Decimal("100000")  # 100 * 1000
    assert disposal.proceeds_fiat == Decimal("150000")  # 100 * 1500
    assert disposal.gain_loss_fiat == Decimal("50000")

    # the USDC received should now be disposable at a cost basis that totals
    # the same 150000 proceeds, spread over 95 units
    usdc_disposal = engine.dispose(USDC, Decimal("95"), Decimal("200000"), T0, "dis-2")
    assert usdc_disposal.cost_basis_fiat == Decimal("150000")


def test_process_acquisition_opens_lot_without_income():
    engine = FifoCostBasisEngine(_oracle(native="1500"))
    event = _event(kind=EventKind.PAYMENT_IN, amount=Decimal("10"))

    result = engine.process([_classified(event, Classification.ACQUISITION)])

    assert result.income_events == []
    disposal = engine.dispose(XLM, Decimal("10"), Decimal("20000"), T0, "dis-1")
    assert disposal.cost_basis_fiat == Decimal("15000")
