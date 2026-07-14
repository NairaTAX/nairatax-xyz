"""Wire ingestion, classification, cost basis, rules, and reporting into one
call — the thing the CLI (and, eventually, an API) invokes end to end.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from nairatax.classification.classifier import classify_events
from nairatax.cost_basis.fifo import FifoCostBasisEngine
from nairatax.ingestion.horizon_client import HorizonClient
from nairatax.ingestion.normalize import normalize_account_activity
from nairatax.models import ClassifiedEvent, TaxReport
from nairatax.pricing import PriceOracle
from nairatax.reporting.builder import build_tax_report
from nairatax.rules.engine import build_tax_line_items
from nairatax.rules.loader import load_rule_pack
from nairatax.rules.schema import RulePack


@dataclass
class PipelineOutcome:
    report: TaxReport
    pack: RulePack
    needs_review: list[ClassifiedEvent]


def run_report_pipeline(
    account: str,
    jurisdiction: str,
    period_start: datetime,
    period_end: datetime,
    horizon_client: HorizonClient,
    price_oracle: PriceOracle,
    own_accounts: frozenset[str] = frozenset(),
) -> PipelineOutcome:
    """Fetch and normalize the full Horizon history of ``account`` plus every
    account in ``own_accounts``, classify the merged stream, run FIFO cost
    basis over all of it (so basis is correct even when the report's period
    is narrower), apply ``jurisdiction``'s rule pack, and build a report for
    ``[period_start, period_end]``.

    All owned accounts' histories are fetched and merged — not just
    ``account`` — because the FIFO engine pools lots per asset across the
    whole portfolio (see ``cost_basis/fifo.py``): a self-transfer out of one
    account is only a correct no-op if that account's earlier acquisitions,
    and whatever the receiving account does with the funds later, are all
    visible to the same engine run.

    The report itself is still labelled with the single ``account`` passed
    in — this reports on one person's tax position, built from the whole
    portfolio's history, not on one wallet in isolation.
    """
    all_own_accounts = own_accounts | {account}

    events = []
    for owned_account in sorted(all_own_accounts):
        events.extend(normalize_account_activity(horizon_client, owned_account))
    events.sort(key=lambda event: event.timestamp)

    classified = classify_events(events, all_own_accounts)

    cost_basis_engine = FifoCostBasisEngine(price_oracle)
    cost_basis_result = cost_basis_engine.process(classified)

    pack = load_rule_pack(jurisdiction)
    line_items = build_tax_line_items(
        pack, cost_basis_result.disposals, cost_basis_result.income_events
    )
    report = build_tax_report(
        account,
        pack,
        period_start,
        period_end,
        line_items,
        needs_review_count=len(cost_basis_result.needs_review),
    )

    return PipelineOutcome(report=report, pack=pack, needs_review=cost_basis_result.needs_review)
