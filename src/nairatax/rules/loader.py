"""Load a :class:`RulePack` from ``rules/packs/<jurisdiction>.yaml``."""

from __future__ import annotations

from pathlib import Path

import yaml

from nairatax.rules.schema import RulePack

PACKS_DIR = Path(__file__).parent / "packs"


class RulePackNotFoundError(FileNotFoundError):
    pass


def load_rule_pack(jurisdiction: str, packs_dir: Path = PACKS_DIR) -> RulePack:
    path = packs_dir / f"{jurisdiction}.yaml"
    if not path.is_file():
        available = sorted(p.stem for p in packs_dir.glob("*.yaml")) if packs_dir.is_dir() else []
        raise RulePackNotFoundError(
            f"no rule pack for jurisdiction {jurisdiction!r} at {path}. "
            f"Available: {', '.join(available) or '(none)'}"
        )
    raw = yaml.safe_load(path.read_text())
    return RulePack.model_validate(raw)
