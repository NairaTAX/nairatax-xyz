import json
from datetime import UTC, datetime
from decimal import Decimal

from nairatax.models import Asset, TaxLineItem, TaxLineItemCategory, TaxReport
from nairatax.reporting.export import to_json

XLM = Asset()
T0 = datetime(2026, 3, 1, tzinfo=UTC)


def _report() -> TaxReport:
    return TaxReport(
        account="GACCOUNT",
        jurisdiction="nigeria",
        currency="NGN",
        period_start=datetime(2026, 1, 1, tzinfo=UTC),
        period_end=datetime(2026, 12, 31, tzinfo=UTC),
        line_items=[
            TaxLineItem(
                event_id="e1",
                date=T0,
                category=TaxLineItemCategory.CAPITAL_GAIN,
                asset=XLM,
                quantity=Decimal("2"),
                amount_fiat=Decimal("1000"),
                tax_owed_fiat=Decimal("150"),
                description="disposal",
            )
        ],
    )


def test_to_json_is_valid_json_with_summary_and_line_items():
    payload = json.loads(to_json(_report()))

    assert payload["account"] == "GACCOUNT"
    assert payload["jurisdiction"] == "nigeria"
    assert payload["summary"]["total_capital_gains"] == "1000"
    assert payload["summary"]["total_tax_owed"] == "150"
    assert len(payload["line_items"]) == 1
    assert payload["line_items"][0]["event_id"] == "e1"


def test_to_json_summary_matches_report_properties():
    report = _report()
    payload = json.loads(to_json(report))
    assert Decimal(payload["summary"]["total_capital_gains"]) == report.total_capital_gains
    assert Decimal(payload["summary"]["total_tax_owed"]) == report.total_tax_owed


def test_to_json_decimals_avoid_scientific_notation():
    report = _report()
    report.line_items[0] = report.line_items[0].model_copy(
        update={"quantity": Decimal("0.0000001")}
    )
    payload = json.loads(to_json(report))
    assert payload["line_items"][0]["quantity"] == "0.0000001"


def test_to_json_empty_report_has_zeroed_summary():
    report = TaxReport(
        account="GACCOUNT",
        jurisdiction="nigeria",
        currency="NGN",
        period_start=datetime(2026, 1, 1, tzinfo=UTC),
        period_end=datetime(2026, 12, 31, tzinfo=UTC),
    )
    payload = json.loads(to_json(report))
    assert payload["summary"]["total_tax_owed"] == "0"
    assert payload["line_items"] == []
