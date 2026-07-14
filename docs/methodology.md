# How NairaTax computes gains, income, and tax owed

This explains the conventions the engine uses, in plain language. It's the
"why" behind `src/nairatax/cost_basis/fifo.py` and
`src/nairatax/rules/engine.py` — read those for the "how."

## Cost basis: FIFO, across your whole portfolio

When you dispose of an asset (sell it, swap it, spend it), the taxable gain
or loss is `proceeds - cost basis`. Cost basis comes from when you
originally acquired the units you're now disposing of.

NairaTax tracks acquisitions as **lots**: a quantity of an asset, the price
you got it at, and when. When you dispose of some amount, it's matched
against your *oldest* lots first — First In, First Out (FIFO). This is the
same method described in the README's Features list, and it's a common,
defensible default where a jurisdiction doesn't mandate a different one
(e.g. specific-identification).

Lots are pooled **per asset across every account you tell NairaTax you
own** — not per account. If you move funds between two of your own Stellar
accounts, that's not a disposal (nothing left your ownership), so it
doesn't touch the lot pool at all. The lot just sits there, unaffected,
regardless of which of your accounts nominally holds the asset on-chain.
This is why `--own-account` matters: without it, a transfer to your other
wallet looks identical to sending money to a stranger, and gets flagged for
review instead of correctly ignored.

## Swaps: a disposal and an acquisition in the same breath

Trading one asset for another on the Stellar DEX (or via a path payment
routed back to yourself) is, for tax purposes, two things happening at
once:

1. You **dispose of** the asset you gave up — proceeds are its value at the
   time of the trade.
2. You **acquire** the asset you received — its cost basis is set to that
   same value.

NairaTax computes the disposal side using the price oracle, and derives the
new lot's cost from *that same figure divided across the units received*,
rather than pricing the received asset independently. That keeps the two
sides of a swap internally consistent — you never end up with a "gain" that
exists only because two independent price lookups didn't quite agree.

## Netting gains and losses, then taxing once

Nigeria doesn't have a separate capital-gains tax rate for this — disposal
gains fold into ordinary personal income tax, computed on **progressive
bands** (see `rules/packs/nigeria.yaml`). That has a real consequence:
you can't correctly compute "the tax on this one transaction" in isolation,
because your marginal rate depends on your *total* chargeable income for
the year.

So NairaTax:

1. Nets every disposal's gain or loss for the period into one number
   (losses reduce the total, floored at zero — this is a simplification;
   see the code comment in `rules/engine.py` for the caveat).
2. Adds total income (things classified `INCOME`, valued at fair market
   value on receipt).
3. Runs *that one number* through the jurisdiction's relief allowance and
   progressive bands to get total tax owed.
4. Splits that total back across the individual ledger lines you see in the
   report, proportionally to each line's share of the taxable base —
   losses always show `0` tax owed, even though they're visible on the
   ledger and did reduce the total.

The per-line number in step 4 is a presentation convenience so you can see
roughly where the tax burden falls. The number that actually matters is the
report's total — and the code guarantees (via a test) that every line's
share always adds back up to exactly that total.

## What NairaTax refuses to guess

A few things are deliberately left blank or routed to `NEEDS_REVIEW` rather
than inferred:

- **A plain inbound transfer from an account you haven't declared as your
  own.** It could be a purchase, income, or a gift — NairaTax has no way to
  know your off-chain intent from the chain alone.
- **A plain outbound transfer to an unknown account.** Could be a sale, a
  spend, or a gift given.
- **`account_merge` operations.** Horizon doesn't report the merged amount
  on the operation itself, only on its effects, which this version doesn't
  resolve — see `ingestion/normalize.py`.
- **Disposing of an asset this account was never seen acquiring.** This
  raises `InsufficientCostBasisError` loudly rather than assuming a `0`
  cost basis, which would silently overstate your gain.

See the README's "Important — Not Tax Advice" section for the broader
point this all serves: NairaTax produces a structured estimate, not a
filing-ready number, and the Nigeria rule pack figures specifically are
still unverified against official guidance.
