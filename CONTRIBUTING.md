# Contributing to NairaTax

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Workflow

```bash
pytest             # run the test suite
ruff check .        # lint
ruff check --fix .  # lint, auto-fixing what's safe to auto-fix
```

Both must pass before opening a PR — CI (`.github/workflows/ci.yml`) runs
the same two commands on every push and PR, across Python 3.11 and 3.12.

## Where things live

See the [Repository Structure](README.md#repository-structure) section of
the README for the package layout, and
[NairaTax Organization](README.md#nairatax-organization) for how this repo
relates to the other repos in the `nairatax-xyz` org.

## Conventions

- **Decimal, never float**, for anything that's a quantity or a monetary
  amount — see `src/nairatax/models.py`. A tax engine that loses precision
  to binary floating point is a tax engine that's wrong.
- **Don't guess.** If a normalizer or classifier can't determine a value
  confidently from the data it has (see `ingestion/normalize.py`'s handling
  of `account_merge`, or the classifier's `NEEDS_REVIEW` category), return
  `None` / flag for review rather than fabricate a plausible-looking number.
- **Rule packs are data, not code.** A change to tax figures belongs in
  `rules/packs/*.yaml`, not in `rules/engine.py`. If a pack's figures
  haven't been confirmed against official guidance, its `verified` field
  must stay `false` — see `rules/packs/nigeria.yaml`.
- **One test module per source module** (`tests/test_<module>.py`), plus
  `tests/test_end_to_end.py` for chain-spanning behaviour. New code needs
  new tests in the same PR, not a follow-up.

## Reporting issues

Open a GitHub issue on this repo. If you're proposing a change to the
Nigeria rule pack figures, cite the specific NRS guidance or Tax Act 2025
provision you're working from — see the "Important — Not Tax Advice"
section of the README for why that matters here specifically.
