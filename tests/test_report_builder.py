from datetime import UTC, datetime
from decimal import Decimal

from nairatax.models import Asset, TaxLineItem, TaxLineItemCategory
from nairatax.reporting.builder import build_tax_report
from nairatax.rules.schema import ConsolidatedRelief, RulePack, TaxBand

XLM = Asset()

PACK = RulePack(
    id="test-simple",
    jurisdiction="testland",
    display_name="Testland",
    currency="TST",
    version="0.1.0",
    verified=False,
    source_note="fixture",
    income_tax_bands=[TaxBand(upper_bound=None, rate=Decimal("0.10"))],
    consolidated_relief=ConsolidatedRelief(
        flat_amount=Decimal("0"),
        minimum_percent_of_gross=Decimal("0"),
        additional_percent_of_gross=Decimal("0"),
    ),
)


def _item(event_id: str, date: datetime, amount: str = "100") -> TaxLineItem:
    return TaxLineItem(
        event_id=event_id,
        date=date,
        category=TaxLineItemCategory.CAPITAL_GAIN,
        asset=XLM,
        quantity=Decimal("1"),
        amount_fiat=Decimal(amount),
        tax_owed_fiat=Decimal(amount) * Decimal("0.10"),
        description="test",
    )


def test_report_only_includes_line_items_within_period():
    period_start = datetime(2026, 1, 1, tzinfo=UTC)
    period_end = datetime(2026, 12, 31, tzinfo=UTC)
    items = [
        _item("before", datetime(2025, 12, 31, tzinfo=UTC)),
        _item("in-period", datetime(2026, 6, 1, tzinfo=UTC)),
        _item("after", datetime(2027, 1, 1, tzinfo=UTC)),
    ]

    report = build_tax_report("GACCOUNT", PACK, period_start, period_end, items)

    assert [item.event_id for item in report.line_items] == ["in-period"]
    assert report.jurisdiction == "testland"
    assert report.currency == "TST"


def test_report_line_items_are_sorted_by_date():
    period_start = datetime(2026, 1, 1, tzinfo=UTC)
    period_end = datetime(2026, 12, 31, tzinfo=UTC)
    items = [
        _item("second", datetime(2026, 6, 1, tzinfo=UTC)),
        _item("first", datetime(2026, 1, 15, tzinfo=UTC)),
    ]

    report = build_tax_report("GACCOUNT", PACK, period_start, period_end, items)

    assert [item.event_id for item in report.line_items] == ["first", "second"]


def test_report_carries_needs_review_count_through():
    period_start = datetime(2026, 1, 1, tzinfo=UTC)
    period_end = datetime(2026, 12, 31, tzinfo=UTC)

    report = build_tax_report(
        "GACCOUNT", PACK, period_start, period_end, [], needs_review_count=3
    )

    assert report.needs_review_count == 3
    assert report.total_tax_owed == Decimal("0")
