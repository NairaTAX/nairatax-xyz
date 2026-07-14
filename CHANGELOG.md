# Changelog

All notable changes to this project are documented here. Format loosely
follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [0.1.0] — Unreleased

Initial prototype of the reference implementation: an end-to-end pipeline
from Stellar Horizon activity to an exported tax report.

### Added

- Horizon ingestion: paginating HTTP client plus normalizers for payments,
  path payments (including self-path-payment swaps), DEX trades, and
  claimable balance create/claim.
- Rule-based event classifier: auto-classifies swaps as disposals and
  transfers between known own accounts as self-transfers; everything else
  is flagged `NEEDS_REVIEW` rather than guessed.
- Portfolio-wide FIFO cost basis engine, pooling lots per asset across every
  account fed into it so self-transfers are a correct no-op.
- Jurisdiction rule pack schema (progressive tax bands + consolidated
  relief) and a Nigeria pack — explicitly `verified: false` pending
  reconciliation with the Tax Act 2025 / NRS Fourth Schedule.
- Rules engine applying a pack to disposals and income, netting gains and
  losses into one chargeable base and allocating the resulting tax
  proportionally back to individual ledger lines.
- Report builder plus CSV and JSON export.
- `nairatax` CLI (`version`, `report`).
- `StaticPriceOracle`: a fixed-rate stand-in for the historical, multi-asset
  fiat pricing adapter that's still on the Roadmap.
- Full pytest suite (unit tests per module plus end-to-end chain tests) and
  a GitHub Actions CI workflow.

### Known limitations

- No real historical fiat pricing — `--price` takes one manual rate per
  asset with no date sensitivity.
- Nigeria rule pack figures are unverified placeholders.
- No review UI: events the classifier flags `NEEDS_REVIEW` have no
  resolution path in this repo yet (planned for `nairatax-web`).
- Single-repo reference implementation; splitting into `nairatax-engine` /
  `nairatax-rules` per the org structure is still pending.
