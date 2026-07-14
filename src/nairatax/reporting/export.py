"""Serialize a :class:`TaxReport` for handoff to a person or an accountant."""

from __future__ import annotations

import csv
import io
from decimal import Decimal

from nairatax.models import TaxReport


def _fixed_point(value: Decimal) -> str:
    """``str(Decimal)`` switches to scientific notation for small magnitudes
    (e.g. ``Decimal("0.0000001")`` -> ``"1E-7"``), which is exact but not
    what a spreadsheet or an accountant expects in a CSV cell.
    """
    return format(value, "f")

CSV_FIELDNAMES = [
    "date",
    "category",
    "asset",
    "quantity",
    "amount_fiat",
    "tax_owed_fiat",
    "description",
    "event_id",
]


def to_csv(report: TaxReport) -> str:
    """Render the per-event ledger as CSV. Deliberately omits the summary
    totals — those belong in the accompanying JSON export or a UI, not mixed
    into a table an accountant will likely import wholesale into a
    spreadsheet.
    """
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=CSV_FIELDNAMES)
    writer.writeheader()
    for item in report.line_items:
        writer.writerow(
            {
                "date": item.date.isoformat(),
                "category": item.category.value,
                "asset": item.asset.id,
                "quantity": _fixed_point(item.quantity),
                "amount_fiat": _fixed_point(item.amount_fiat),
                "tax_owed_fiat": _fixed_point(item.tax_owed_fiat),
                "description": item.description,
                "event_id": item.event_id,
            }
        )
    return buffer.getvalue()
