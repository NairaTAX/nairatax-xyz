"""Assemble the final :class:`TaxReport` from a rule pack's ledger lines."""

from __future__ import annotations

from datetime import datetime

from nairatax.models import TaxLineItem, TaxReport
from nairatax.rules.schema import RulePack


def build_tax_report(
    account: str,
    pack: RulePack,
    period_start: datetime,
    period_end: datetime,
    line_items: list[TaxLineItem],
    needs_review_count: int = 0,
) -> TaxReport:
    """Filter ``line_items`` to the reporting period and assemble a
    :class:`TaxReport`. ``line_items`` is typically the output of
    :func:`nairatax.rules.engine.build_tax_line_items`, computed over the
    full available history so cost basis is correct — this is where that
    full ledger gets narrowed down to one filing period.
    """
    in_period = [item for item in line_items if period_start <= item.date <= period_end]
    return TaxReport(
        account=account,
        jurisdiction=pack.jurisdiction,
        currency=pack.currency,
        period_start=period_start,
        period_end=period_end,
        line_items=sorted(in_period, key=lambda item: item.date),
        needs_review_count=needs_review_count,
    )
