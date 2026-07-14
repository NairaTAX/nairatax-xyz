"""Sanity checks for the shipped Nigeria rule pack.

These deliberately do NOT assert specific tax figures are "correct" — the
pack is explicitly unverified (see rules/packs/nigeria.yaml) — only that it
loads, is internally consistent, and is honest about its own status.
"""

from decimal import Decimal

from nairatax.rules.loader import load_rule_pack


def test_nigeria_pack_loads():
    pack = load_rule_pack("nigeria")
    assert pack.jurisdiction == "nigeria"
    assert pack.currency == "NGN"


def test_nigeria_pack_is_explicitly_flagged_unverified():
    pack = load_rule_pack("nigeria")
    assert pack.verified is False
    assert "confirm" in pack.source_note.lower()


def test_nigeria_pack_bands_are_progressive_and_end_unbounded():
    pack = load_rule_pack("nigeria")
    rates = [band.rate for band in pack.income_tax_bands]
    assert rates == sorted(rates)  # strictly non-decreasing marginal rates
    assert pack.income_tax_bands[-1].upper_bound is None


def test_nigeria_pack_relief_matches_documented_cra_shape():
    pack = load_rule_pack("nigeria")
    relief = pack.consolidated_relief
    assert relief.flat_amount == Decimal("200000")
    assert relief.additional_percent_of_gross == Decimal("0.20")
