"""Rule-based classification of normalized events.

This classifier only makes calls that are structurally unambiguous from
on-chain data alone:

- A swap (a DEX trade, or a path payment routed back to the same account)
  disposes of one asset to acquire another at a known on-chain value — that's
  a disposal by construction, no human input needed.
- A transfer between two of the user's own accounts is a self-transfer, not
  a taxable event — but only knowable if the caller tells us which accounts
  it owns.

Everything else — a plain inbound transfer from an unknown account, or a
plain outbound transfer to one — could be a purchase, income, a gift, or a
sale/spend, and telling those apart requires context this engine doesn't
have (off-chain consideration, the sender/recipient's intent). Rather than
guess, those events come back as ``NEEDS_REVIEW`` with a reason describing
the choice a human needs to make. This is the "review step so nothing is
guessed silently" the product description promises.
"""

from __future__ import annotations

from nairatax.models import Classification, ClassifiedEvent, EventKind, NormalizedEvent

_INFLOW_KINDS = frozenset(
    {EventKind.PAYMENT_IN, EventKind.PATH_PAYMENT_IN, EventKind.CLAIMABLE_BALANCE_CLAIM}
)
_OUTFLOW_KINDS = frozenset(
    {EventKind.PAYMENT_OUT, EventKind.PATH_PAYMENT_OUT, EventKind.CLAIMABLE_BALANCE_CREATE}
)


def _classify_swap(event: NormalizedEvent) -> tuple[Classification, str]:
    return (
        Classification.DISPOSAL,
        f"On-chain swap: disposes of {event.amount} {event.asset.id} to acquire "
        f"{event.counter_amount} {event.counter_asset.id if event.counter_asset else '?'}.",
    )


def _classify_inflow(
    event: NormalizedEvent, own_accounts: frozenset[str]
) -> tuple[Classification, str]:
    if event.counterparty is not None and event.counterparty in own_accounts:
        return Classification.SELF_TRANSFER, "Received from another account you control."
    return (
        Classification.NEEDS_REVIEW,
        "Inbound transfer from an external account — confirm whether this is a "
        "purchase (acquisition), income, or a gift received.",
    )


def _classify_outflow(
    event: NormalizedEvent, own_accounts: frozenset[str]
) -> tuple[Classification, str]:
    if event.counterparty is not None and event.counterparty in own_accounts:
        return Classification.SELF_TRANSFER, "Sent to another account you control."
    return (
        Classification.NEEDS_REVIEW,
        "Outbound transfer to an external account — confirm whether this is a "
        "disposal (sale/spend) or a gift given.",
    )


def classify_event(event: NormalizedEvent, own_accounts: frozenset[str]) -> ClassifiedEvent:
    """Classify a single event. ``own_accounts`` should include the account
    the event stream was fetched for plus any other Stellar accounts the same
    user controls, so transfers between them are recognised as non-taxable.
    """
    is_self_swap = event.kind is EventKind.PATH_PAYMENT_OUT and event.counter_asset is not None

    if event.kind is EventKind.TRADE or is_self_swap:
        classification, reason = _classify_swap(event)
    elif event.kind in _INFLOW_KINDS:
        classification, reason = _classify_inflow(event, own_accounts)
    elif event.kind in _OUTFLOW_KINDS:
        classification, reason = _classify_outflow(event, own_accounts)
    else:  # pragma: no cover - defensive: every current EventKind is handled above
        raise AssertionError(f"unhandled EventKind: {event.kind!r}")

    return ClassifiedEvent(event=event, classification=classification, reason=reason)


def classify_events(
    events: list[NormalizedEvent], own_accounts: set[str] | frozenset[str]
) -> list[ClassifiedEvent]:
    """Classify a full event stream. Order is preserved."""
    accounts = frozenset(own_accounts)
    return [classify_event(event, accounts) for event in events]
