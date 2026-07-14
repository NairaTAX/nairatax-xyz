from decimal import Decimal

import pytest
import yaml

from nairatax.rules.loader import RulePackNotFoundError, load_rule_pack
from nairatax.rules.schema import ConsolidatedRelief, RulePack, TaxBand

VALID_PACK = {
    "id": "testland-2026",
    "jurisdiction": "testland",
    "display_name": "Testland",
    "currency": "TST",
    "version": "0.1.0",
    "verified": False,
    "source_note": "fixture pack for tests",
    "income_tax_bands": [
        {"upper_bound": "1000", "rate": "0.10"},
        {"upper_bound": None, "rate": "0.20"},
    ],
    "consolidated_relief": {
        "flat_amount": "100",
        "minimum_percent_of_gross": "0.01",
        "additional_percent_of_gross": "0.20",
    },
}


def test_valid_pack_parses():
    pack = RulePack.model_validate(VALID_PACK)
    assert pack.income_tax_bands[0].rate == Decimal("0.10")
    assert pack.income_tax_bands[-1].upper_bound is None


def test_consolidated_relief_uses_higher_of_flat_or_percent_floor():
    relief = ConsolidatedRelief(
        flat_amount=Decimal("200000"),
        minimum_percent_of_gross=Decimal("0.01"),
        additional_percent_of_gross=Decimal("0.20"),
    )
    # 1% of 10,000,000 = 100,000 < flat 200,000 -> flat wins
    assert relief.compute(Decimal("10000000")) == Decimal("200000") + Decimal("2000000")
    # 1% of 100,000,000 = 1,000,000 > flat 200,000 -> percent wins
    assert relief.compute(Decimal("100000000")) == Decimal("1000000") + Decimal("20000000")


def test_last_band_must_be_unbounded():
    bad = {**VALID_PACK, "income_tax_bands": [{"upper_bound": "1000", "rate": "0.10"}]}
    with pytest.raises(ValueError, match="unbounded"):
        RulePack.model_validate(bad)


def test_only_last_band_may_be_unbounded():
    bad = {
        **VALID_PACK,
        "income_tax_bands": [
            {"upper_bound": None, "rate": "0.10"},
            {"upper_bound": None, "rate": "0.20"},
        ],
    }
    with pytest.raises(ValueError, match="only the last"):
        RulePack.model_validate(bad)


def test_bands_must_be_strictly_increasing():
    bad = {
        **VALID_PACK,
        "income_tax_bands": [
            {"upper_bound": "1000", "rate": "0.10"},
            {"upper_bound": "500", "rate": "0.15"},
            {"upper_bound": None, "rate": "0.20"},
        ],
    }
    with pytest.raises(ValueError, match="strictly increasing"):
        RulePack.model_validate(bad)


def test_load_rule_pack_reads_yaml_from_packs_dir(tmp_path):
    (tmp_path / "testland.yaml").write_text(yaml.safe_dump(VALID_PACK))
    pack = load_rule_pack("testland", packs_dir=tmp_path)
    assert pack.id == "testland-2026"


def test_load_rule_pack_missing_jurisdiction_raises_with_available_list(tmp_path):
    (tmp_path / "testland.yaml").write_text(yaml.safe_dump(VALID_PACK))
    with pytest.raises(RulePackNotFoundError, match="testland"):
        load_rule_pack("nowhere", packs_dir=tmp_path)


def test_tax_band_model_accepts_decimal_strings():
    band = TaxBand(upper_bound="300000", rate="0.07")
    assert band.upper_bound == Decimal("300000")
