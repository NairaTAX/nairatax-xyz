import csv
import io
from datetime import UTC, datetime
from decimal import Decimal

from nairatax.models import (
    Asset,
    TaxLineItem,
    TaxLineItemCategory,
    TaxReport,
)
from nairatax.reporting.export import to_csv

XLM = Asset()
T0 = datetime(2026, 3, 1, tzinfo=UTC)


def _report(line_items) -> TaxReport:
    return TaxReport(
        account="GACCOUNT",
        jurisdiction="nigeria",
        currency="NGN",
        period_start=datetime(2026, 1, 1, tzinfo=UTC),
        period_end=datetime(2026, 12, 31, tzinfo=UTC),
        line_items=line_items,
    )


def test_to_csv_has_expected_header_and_row_count():
    items = [
        TaxLineItem(
            event_id="e1",
            date=T0,
            category=TaxLineItemCategory.CAPITAL_GAIN,
            asset=XLM,
            quantity=Decimal("2.5000000"),
            amount_fiat=Decimal("1000.50"),
            tax_owed_fiat=Decimal("100.05"),
            description="Disposal of 2.5 native",
        )
    ]
    csv_text = to_csv(_report(items))
    rows = list(csv.DictReader(io.StringIO(csv_text)))

    assert len(rows) == 1
    assert rows[0]["event_id"] == "e1"
    assert rows[0]["asset"] == "native"
    assert rows[0]["amount_fiat"] == "1000.50"
    assert rows[0]["category"] == "capital_gain"


def test_to_csv_with_no_line_items_is_header_only():
    csv_text = to_csv(_report([]))
    rows = list(csv.DictReader(io.StringIO(csv_text)))
    assert rows == []
    assert "event_id" in csv_text


def test_to_csv_preserves_decimal_precision_as_text():
    items = [
        TaxLineItem(
            event_id="e1",
            date=T0,
            category=TaxLineItemCategory.INCOME,
            asset=XLM,
            quantity=Decimal("0.0000001"),
            amount_fiat=Decimal("0.01"),
            tax_owed_fiat=Decimal("0.001"),
            description="dust",
        )
    ]
    csv_text = to_csv(_report(items))
    rows = list(csv.DictReader(io.StringIO(csv_text)))
    assert rows[0]["quantity"] == "0.0000001"
    assert rows[0]["tax_owed_fiat"] == "0.001"
