"""Apply a :class:`RulePack` to a set of disposals and income events.

Nigeria folds crypto disposal gains into ordinary personal income tax rather
than taxing them at a separate flat capital-gains rate (see the README), so
tax is computed once over the whole chargeable base — net capital gains plus
income — using the pack's progressive bands. That total is then allocated
back down to individual :class:`TaxLineItem` rows for the report, since a
progressive, netted tax total doesn't belong to any one transaction by
construction. See :func:`build_tax_line_items` for exactly how that
allocation is done and why.
"""

from __future__ import annotations

from decimal import Decimal

from nairatax.models import Disposal, IncomeEvent, TaxLineItem, TaxLineItemCategory
from nairatax.rules.schema import RulePack


def compute_tax(pack: RulePack, chargeable_income: Decimal) -> Decimal:
    """Total tax owed on ``chargeable_income`` (already net of relief is NOT
    assumed — the pack's consolidated relief is applied here) under the
    pack's progressive bands.
    """
    if chargeable_income <= 0:
        return Decimal("0")

    relief = pack.consolidated_relief.compute(chargeable_income)
    taxable = max(chargeable_income - relief, Decimal("0"))

    tax = Decimal("0")
    previous_bound = Decimal("0")
    for band in pack.income_tax_bands:
        if band.upper_bound is None:
            tax += max(taxable - previous_bound, Decimal("0")) * band.rate
            break
        band_amount = max(min(taxable, band.upper_bound) - previous_bound, Decimal("0"))
        tax += band_amount * band.rate
        previous_bound = band.upper_bound
        if taxable <= previous_bound:
            break
    return tax


def build_tax_line_items(
    pack: RulePack,
    disposals: list[Disposal],
    income_events: list[IncomeEvent],
) -> list[TaxLineItem]:
    """Build the per-event ledger, with tax allocated proportionally within
    each category.

    Net capital gains (gains minus losses, floored at zero) and total income
    are combined into one chargeable base and taxed once via
    :func:`compute_tax`. That total is then split between the two
    categories in proportion to each category's share of the base, and
    within the capital-gains category, split again across only the
    *gaining* disposals in proportion to their gain — loss disposals still
    appear on the ledger (so the netting is visible) but are never
    themselves allocated a positive tax amount.

    This allocation is a presentation convenience, not a second source of
    truth: ``TaxReport.total_tax_owed`` (the sum of these allocations) always
    equals the one number ``compute_tax`` produced for the whole base.
    """
    net_capital_gain = max(sum((d.gain_loss_fiat for d in disposals), Decimal("0")), Decimal("0"))
    total_income = sum((i.fair_market_value_fiat for i in income_events), Decimal("0"))
    chargeable_income = net_capital_gain + total_income
    total_tax = compute_tax(pack, chargeable_income)

    if chargeable_income > 0:
        capital_gains_tax_pool = total_tax * (net_capital_gain / chargeable_income)
        income_tax_pool = total_tax * (total_income / chargeable_income)
    else:
        capital_gains_tax_pool = Decimal("0")
        income_tax_pool = Decimal("0")

    total_positive_gains = sum(
        (d.gain_loss_fiat for d in disposals if d.gain_loss_fiat > 0), Decimal("0")
    )

    line_items: list[TaxLineItem] = []

    for disposal in disposals:
        if disposal.gain_loss_fiat > 0 and total_positive_gains > 0:
            tax_owed = capital_gains_tax_pool * (disposal.gain_loss_fiat / total_positive_gains)
        else:
            tax_owed = Decimal("0")
        line_items.append(
            TaxLineItem(
                event_id=disposal.event_id,
                date=disposal.disposed_at,
                category=TaxLineItemCategory.CAPITAL_GAIN,
                asset=disposal.asset,
                quantity=disposal.quantity,
                amount_fiat=disposal.gain_loss_fiat,
                tax_owed_fiat=tax_owed,
                description=f"Disposal of {disposal.quantity} {disposal.asset.id}",
            )
        )

    for income in income_events:
        tax_owed = (
            income_tax_pool * (income.fair_market_value_fiat / total_income)
            if total_income > 0
            else Decimal("0")
        )
        line_items.append(
            TaxLineItem(
                event_id=income.event_id,
                date=income.received_at,
                category=TaxLineItemCategory.INCOME,
                asset=income.asset,
                quantity=income.quantity,
                amount_fiat=income.fair_market_value_fiat,
                tax_owed_fiat=tax_owed,
                description=f"Income: {income.quantity} {income.asset.id}",
            )
        )

    return line_items
