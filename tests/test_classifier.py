from datetime import UTC, datetime
from decimal import Decimal

from nairatax.classification.classifier import classify_event, classify_events
from nairatax.models import Asset, Classification, EventKind, NormalizedEvent

ME = "GMEXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX"
MY_OTHER_WALLET = "GMYOTHERXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX"
STRANGER = "GSTRANGERXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX"
ISSUER = "GISSUERXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX"

OWN_ACCOUNTS = frozenset({ME, MY_OTHER_WALLET})


def _event(**overrides) -> NormalizedEvent:
    defaults = dict(
        event_id="e1",
        account=ME,
        timestamp=datetime(2026, 3, 1, tzinfo=UTC),
        kind=EventKind.PAYMENT_IN,
        asset=Asset(),
        amount=Decimal("10"),
        source_operation_id="op-1",
    )
    defaults.update(overrides)
    return NormalizedEvent(**defaults)


def test_trade_is_a_disposal():
    event = _event(
        kind=EventKind.TRADE,
        counter_asset=Asset(code="USDC", issuer=ISSUER),
        counter_amount=Decimal("5"),
        counterparty=STRANGER,
    )
    result = classify_event(event, OWN_ACCOUNTS)
    assert result.classification is Classification.DISPOSAL
    assert "swap" in result.reason.lower()


def test_self_path_payment_swap_is_a_disposal():
    event = _event(
        kind=EventKind.PATH_PAYMENT_OUT,
        counter_asset=Asset(code="USDC", issuer=ISSUER),
        counter_amount=Decimal("5"),
        counterparty=ME,
    )
    assert classify_event(event, OWN_ACCOUNTS).classification is Classification.DISPOSAL


def test_path_payment_out_without_counter_asset_needs_review():
    event = _event(kind=EventKind.PATH_PAYMENT_OUT, counterparty=STRANGER)
    result = classify_event(event, OWN_ACCOUNTS)
    assert result.classification is Classification.NEEDS_REVIEW
    assert "disposal" in result.reason.lower() or "gift" in result.reason.lower()


def test_inflow_from_own_account_is_self_transfer():
    event = _event(kind=EventKind.PAYMENT_IN, counterparty=MY_OTHER_WALLET)
    result = classify_event(event, OWN_ACCOUNTS)
    assert result.classification is Classification.SELF_TRANSFER


def test_inflow_from_stranger_needs_review():
    event = _event(kind=EventKind.PAYMENT_IN, counterparty=STRANGER)
    result = classify_event(event, OWN_ACCOUNTS)
    assert result.classification is Classification.NEEDS_REVIEW
    assert "income" in result.reason.lower() or "gift" in result.reason.lower()


def test_outflow_to_own_account_is_self_transfer():
    event = _event(kind=EventKind.PAYMENT_OUT, counterparty=MY_OTHER_WALLET)
    result = classify_event(event, OWN_ACCOUNTS)
    assert result.classification is Classification.SELF_TRANSFER


def test_outflow_to_stranger_needs_review():
    event = _event(kind=EventKind.PAYMENT_OUT, counterparty=STRANGER)
    result = classify_event(event, OWN_ACCOUNTS)
    assert result.classification is Classification.NEEDS_REVIEW


def test_claimable_balance_claim_has_no_counterparty_and_needs_review():
    event = _event(kind=EventKind.CLAIMABLE_BALANCE_CLAIM, counterparty=None)
    result = classify_event(event, OWN_ACCOUNTS)
    assert result.classification is Classification.NEEDS_REVIEW


def test_claimable_balance_create_to_own_account_is_self_transfer():
    event = _event(kind=EventKind.CLAIMABLE_BALANCE_CREATE, counterparty=MY_OTHER_WALLET)
    result = classify_event(event, OWN_ACCOUNTS)
    assert result.classification is Classification.SELF_TRANSFER


def test_classify_events_preserves_order():
    events = [
        _event(event_id="a", kind=EventKind.PAYMENT_IN, counterparty=STRANGER),
        _event(event_id="b", kind=EventKind.PAYMENT_OUT, counterparty=MY_OTHER_WALLET),
    ]
    results = classify_events(events, OWN_ACCOUNTS)
    assert [r.event.event_id for r in results] == ["a", "b"]
    assert results[1].classification is Classification.SELF_TRANSFER
