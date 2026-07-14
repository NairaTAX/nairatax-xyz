"""Schema for a jurisdiction rule pack.

Rule packs are data (YAML under ``rules/packs/``), not Python conditionals —
per the README: "Jurisdiction rule packs live as auditable data, not magic
numbers." This module is only the shape of that data; ``loader.py`` reads it
and ``engine.py`` applies it.
"""

from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, ConfigDict, model_validator


class TaxBand(BaseModel):
    """One slice of a progressive tax schedule: the rate applied to
    chargeable income between the previous band's ``upper_bound`` and this
    one's. ``upper_bound=None`` marks the top, unbounded band.
    """

    model_config = ConfigDict(frozen=True)

    upper_bound: Decimal | None
    rate: Decimal


class ConsolidatedRelief(BaseModel):
    """Nigeria's Consolidated Relief Allowance shape: the higher of a flat
    amount or a minimum percentage of gross income, plus a further
    percentage of gross income — both deducted from gross income before the
    progressive bands are applied.
    """

    model_config = ConfigDict(frozen=True)

    flat_amount: Decimal
    minimum_percent_of_gross: Decimal
    additional_percent_of_gross: Decimal

    def compute(self, gross_income: Decimal) -> Decimal:
        floor = max(self.flat_amount, gross_income * self.minimum_percent_of_gross)
        return floor + gross_income * self.additional_percent_of_gross


class RulePack(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    jurisdiction: str
    display_name: str
    currency: str
    version: str
    verified: bool
    """False means these figures have not been confirmed against current
    official guidance and MUST NOT be relied on to file a return — see
    ``source_note``."""
    source_note: str
    income_tax_bands: list[TaxBand]
    consolidated_relief: ConsolidatedRelief

    @model_validator(mode="after")
    def _bands_are_increasing_and_unbounded_band_is_last(self) -> RulePack:
        bounds = [band.upper_bound for band in self.income_tax_bands]
        if not bounds or bounds[-1] is not None:
            raise ValueError("the last income tax band must be unbounded (upper_bound: null)")
        if any(bound is None for bound in bounds[:-1]):
            raise ValueError("only the last income tax band may be unbounded")
        finite_bounds = bounds[:-1]
        if finite_bounds != sorted(finite_bounds) or len(set(finite_bounds)) != len(finite_bounds):
            raise ValueError("income tax band upper_bounds must be strictly increasing")
        return self
