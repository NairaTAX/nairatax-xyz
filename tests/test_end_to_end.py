"""Full-chain tests: classified events all the way through to exported
report text. Complements the unit tests per module and test_pipeline.py
(which exercises ingestion + classification but, by design, never produces
a disposal — see the second test below for why).
"""

import json
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from nairatax.classification.classifier import classify_events
from nairatax.cost_basis.fifo import FifoCostBasisEngine, InsufficientCostBasisError
from nairatax.ingestion.normalize import normalize_account_activity
from nairatax.models import Asset, Classification, ClassifiedEvent, EventKind, NormalizedEvent
from nairatax.pricing import StaticPriceOracle
from nairatax.reporting.builder import build_tax_report
from nairatax.reporting.export import to_csv, to_json
from nairatax.rules.engine import build_tax_line_items
from nairatax.rules.loader import load_rule_pack

ACCOUNT = "GACCOUNTXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX"
STRANGER = "GSTRANGERXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX"
XLM = Asset()
USDC = Asset(code="USDC", issuer="GISSUERXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX")


def _classified_event(
    event_id: str, kind: EventKind, classification: Classification, when: datetime, **overrides
) -> ClassifiedEvent:
    defaults = dict(
        event_id=event_id,
        account=ACCOUNT,
        timestamp=when,
        kind=kind,
        asset=XLM,
        amount=Decimal("100"),
        source_operation_id=event_id,
    )
    defaults.update(overrides)
    event = NormalizedEvent(**defaults)
    return ClassifiedEvent(event=event, classification=classification, reason="test fixture")


def test_full_chain_from_classified_events_to_exported_report():
    t_acquire = datetime(2026, 1, 10, tzinfo=UTC)
    t_swap = datetime(2026, 3, 1, tzinfo=UTC)
    t_income = datetime(2026, 6, 1, tzinfo=UTC)

    classified_events = [
        _classified_event("acq-1", EventKind.PAYMENT_IN, Classification.ACQUISITION, t_acquire),
        _classified_event(
            "swap-1",
            EventKind.TRADE,
            Classification.DISPOSAL,
            t_swap,
            counter_asset=USDC,
            counter_amount=Decimal("95"),
            counterparty=STRANGER,
        ),
        _classified_event(
            "income-1",
            EventKind.PAYMENT_IN,
            Classification.INCOME,
            t_income,
            # Large enough that, after Nigeria's consolidated relief
            # allowance is deducted, there's still a positive taxable
            # amount left — a small income entirely absorbed by relief
            # would make this test's `total_tax_owed > 0` assertion
            # meaningless rather than wrong.
            amount=Decimal("2000"),
        ),
    ]

    engine = FifoCostBasisEngine(StaticPriceOracle({"native": Decimal("1000")}))
    result = engine.process(classified_events)

    pack = load_rule_pack("nigeria")
    line_items = build_tax_line_items(pack, result.disposals, result.income_events)
    report = build_tax_report(
        ACCOUNT,
        pack,
        datetime(2026, 1, 1, tzinfo=UTC),
        datetime(2026, 12, 31, tzinfo=UTC),
        line_items,
        needs_review_count=len(result.needs_review),
    )

    assert report.needs_review_count == 0
    assert len(report.line_items) == 2  # one disposal, one income line
    assert report.total_tax_owed > 0
    # the allocation invariant proven in test_rules_engine.py must hold here too
    allocated_total = sum((li.tax_owed_fiat for li in report.line_items), Decimal("0"))
    assert allocated_total == report.total_tax_owed

    csv_text = to_csv(report)
    assert csv_text.count("\n") == 3  # header + 2 rows (+trailing newline)

    json_payload = json.loads(to_json(report))
    assert Decimal(json_payload["summary"]["total_tax_owed"]) == report.total_tax_owed
    assert len(json_payload["line_items"]) == 2


def test_disposing_never_acquired_funds_fails_loudly_not_silently():
    """The classifier never invents an acquisition, so a trade that disposes
    of an asset this account was never seen acquiring must raise rather than
    quietly report a $0-cost-basis (and therefore inflated) gain.
    """
    events = normalize_account_activity(
        _FakeClientWithOneUnbackedTrade(), ACCOUNT
    )
    classified = classify_events(events, frozenset({ACCOUNT}))

    engine = FifoCostBasisEngine(StaticPriceOracle({"native": Decimal("1000")}))
    with pytest.raises(InsufficientCostBasisError):
        engine.process(classified)


class _FakeClientWithOneUnbackedTrade:
    def iter_payments(self, account_id):
        return iter([])

    def iter_trades(self, account_id):
        return iter(
            [
                {
                    "id": "t1",
                    "ledger_close_time": "2026-03-01T00:00:00Z",
                    "base_account": ACCOUNT,
                    "base_asset_type": "native",
                    "base_amount": "100",
                    "base_is_seller": True,
                    "counter_account": STRANGER,
                    "counter_asset_type": "credit_alphanum4",
                    "counter_asset_code": "USDC",
                    "counter_asset_issuer": USDC.issuer,
                    "counter_amount": "95",
                    "base_offer_id": "1",
                }
            ]
        )

    def iter_operations(self, account_id):
        return iter([])

    def get_operation_effects(self, operation_id):
        return []
