# NairaTax — cross-repo map

Working notes on how the six repos in the `nairatax-xyz` GitHub org fit
together. This file is scratch — its content gets folded into `README.md`
and this file is then deleted.

## Repos

| Repo | Purpose | Primary language | Depends on |
|------|---------|-------------------|------------|
| [`nairatax-xyz`](https://github.com/nairatax-xyz/nairatax-xyz) | Org landing page, this README, roadmap, project board. Also currently home to the reference implementation of the ingestion/classification/cost-basis/rules pipeline (`src/nairatax/`) until it's split out. | Python | — |
| [`nairatax-web`](https://github.com/nairatax-xyz/nairatax-web) | Frontend app — dashboard, review/tag UI for NEEDS_REVIEW events, reports, export | TypeScript/React | `nairatax-engine` (via its API) |
| [`nairatax-engine`](https://github.com/nairatax-xyz/nairatax-engine) | Ledger ingestion, event classification, FIFO cost basis, rules application | Python | `nairatax-rules` (rule pack data) |
| [`nairatax-rules`](https://github.com/nairatax-xyz/nairatax-rules) | Jurisdiction rule packs as auditable data (e.g. `nigeria-nta-2025`) | YAML/data | — |
| [`nairatax-contracts`](https://github.com/nairatax-xyz/nairatax-contracts) | *(optional)* Soroban contracts, if an on-chain component is added | Rust (Soroban) | — |
| [`nairatax-docs`](https://github.com/nairatax-xyz/nairatax-docs) | Methodology, filing guides, developer + user docs | Markdown | — |

## How they connect

```
Stellar Horizon
      │
      ▼
nairatax-engine   (ingest → classify → cost basis)
      │
      ├──▶ nairatax-rules   (jurisdiction rule packs)
      │
      ▼
nairatax-web   (review, report, export)
      │
      ▼
nairatax-contracts   (optional, on-chain)
```

## Shared contracts (must stay in sync across repos)

Not yet formally specified — as `nairatax-engine` and `nairatax-rules` are
split out of this repo's reference implementation, the event schema
(`NormalizedEvent`: `in` / `out` / `swap`) and the rule-pack format
(`RulePack`: progressive bands + consolidated relief, currently in
`src/nairatax/rules/schema.py`) become the cross-repo contracts to keep in
sync. If a change in one repo touches either shape, call it out so the
matching repo can be updated in the same change set.

## Conventions for AI agents

- Treat the repo table above as the source of truth for which repo owns
  what; each repo's own README covers repo-local conventions.
- The rule packs under `rules/packs/*.yaml` are data, not code — a change to
  tax figures there should never require a Python code change, and vice
  versa.
- Rule packs may be `verified: false` (see `nigeria.yaml`) — never present
  an unverified pack's output as filing-ready; that flag exists so tooling
  and humans downstream can tell the difference.
