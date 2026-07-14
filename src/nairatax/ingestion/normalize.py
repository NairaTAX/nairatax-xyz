"""Turn raw Horizon JSON records into :class:`NormalizedEvent` objects.

Each ``normalize_*`` function is a pure function over one raw record plus the
account being processed — no I/O — so they're trivial to unit test with
fixture dicts. :func:`normalize_account_activity` is the only function here
that talks to a :class:`HorizonClient`.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from nairatax.models import Asset, EventKind, NormalizedEvent

if TYPE_CHECKING:
    from nairatax.ingestion.horizon_client import HorizonClient


def _parse_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _asset_from_split_fields(raw: dict[str, Any], prefix: str = "") -> Asset:
    """Payment-shaped operations split an asset across ``{prefix}asset_type``,
    ``{prefix}asset_code``, and ``{prefix}asset_issuer`` fields.
    """
    asset_type = raw.get(f"{prefix}asset_type", "native")
    if asset_type == "native":
        return Asset()
    return Asset(code=raw[f"{prefix}asset_code"], issuer=raw[f"{prefix}asset_issuer"])


def _asset_from_canonical(value: str) -> Asset:
    """Claimable-balance operations and effects instead give the asset as one
    canonical string: ``"native"`` or ``"CODE:ISSUER"``.
    """
    if value == "native":
        return Asset()
    code, issuer = value.split(":", 1)
    return Asset(code=code, issuer=issuer)


def normalize_payment(raw: dict[str, Any], account_id: str) -> NormalizedEvent | None:
    """Normalize one record from the Horizon ``/payments`` feed: ``payment``,
    ``path_payment_strict_send``/``receive``, or ``create_account``.

    Returns ``None`` for operation types this normalizer can't safely
    represent — currently ``account_merge``, since Horizon does not report
    the merged amount on the operation resource itself (only on its effects),
    and guessing would put a fabricated number in a tax report.
    """
    op_type = raw["type"]
    timestamp = _parse_timestamp(raw["created_at"])
    event_id = f"payment:{raw['id']}"

    if op_type == "payment":
        asset = _asset_from_split_fields(raw)
        amount = Decimal(raw["amount"])
        if raw["from"] == account_id:
            return NormalizedEvent(
                event_id=event_id,
                account=account_id,
                timestamp=timestamp,
                kind=EventKind.PAYMENT_OUT,
                asset=asset,
                amount=amount,
                counterparty=raw["to"],
                source_operation_id=raw["id"],
            )
        if raw["to"] == account_id:
            return NormalizedEvent(
                event_id=event_id,
                account=account_id,
                timestamp=timestamp,
                kind=EventKind.PAYMENT_IN,
                asset=asset,
                amount=amount,
                counterparty=raw["from"],
                source_operation_id=raw["id"],
            )
        return None

    if op_type in ("path_payment_strict_send", "path_payment_strict_receive"):
        dest_asset = _asset_from_split_fields(raw)
        dest_amount = Decimal(raw["amount"])
        source_asset = _asset_from_split_fields(raw, prefix="source_")
        source_amount = Decimal(raw["source_amount"])
        is_sender = raw["from"] == account_id
        is_recipient = raw["to"] == account_id

        if is_sender and is_recipient:
            # Self path payment: a swap of source_asset for dest_asset within
            # one account, e.g. converting XLM to USDC via the DEX in one op.
            return NormalizedEvent(
                event_id=event_id,
                account=account_id,
                timestamp=timestamp,
                kind=EventKind.PATH_PAYMENT_OUT,
                asset=source_asset,
                amount=source_amount,
                counter_asset=dest_asset,
                counter_amount=dest_amount,
                counterparty=account_id,
                source_operation_id=raw["id"],
            )
        if is_sender:
            return NormalizedEvent(
                event_id=event_id,
                account=account_id,
                timestamp=timestamp,
                kind=EventKind.PATH_PAYMENT_OUT,
                asset=source_asset,
                amount=source_amount,
                counterparty=raw["to"],
                source_operation_id=raw["id"],
            )
        if is_recipient:
            return NormalizedEvent(
                event_id=event_id,
                account=account_id,
                timestamp=timestamp,
                kind=EventKind.PATH_PAYMENT_IN,
                asset=dest_asset,
                amount=dest_amount,
                counterparty=raw["from"],
                source_operation_id=raw["id"],
            )
        return None

    if op_type == "create_account":
        amount = Decimal(raw["starting_balance"])
        if raw["funder"] == account_id:
            return NormalizedEvent(
                event_id=event_id,
                account=account_id,
                timestamp=timestamp,
                kind=EventKind.PAYMENT_OUT,
                asset=Asset(),
                amount=amount,
                counterparty=raw["account"],
                source_operation_id=raw["id"],
            )
        if raw["account"] == account_id:
            return NormalizedEvent(
                event_id=event_id,
                account=account_id,
                timestamp=timestamp,
                kind=EventKind.PAYMENT_IN,
                asset=Asset(),
                amount=amount,
                counterparty=raw["funder"],
                source_operation_id=raw["id"],
            )
        return None

    # account_merge and any future/unknown payment-feed operation type.
    return None


def normalize_trade(raw: dict[str, Any], account_id: str) -> NormalizedEvent | None:
    """Normalize one record from the Horizon ``/trades`` feed.

    A trade always settles as: ``base_account`` gives up ``base_amount`` of
    ``base_asset`` and receives ``counter_amount`` of ``counter_asset``, and
    vice versa for ``counter_account`` — regardless of ``base_is_seller``,
    which only records the original offer's buy/sell direction for
    bookkeeping, not which side of the settlement each account is on.
    """
    base_asset = _asset_from_split_fields(raw, prefix="base_")
    counter_asset = _asset_from_split_fields(raw, prefix="counter_")
    base_amount = Decimal(raw["base_amount"])
    counter_amount = Decimal(raw["counter_amount"])

    if raw["base_account"] == account_id:
        given_asset, given_amount = base_asset, base_amount
        received_asset, received_amount = counter_asset, counter_amount
        counterparty = raw.get("counter_account")
    elif raw["counter_account"] == account_id:
        given_asset, given_amount = counter_asset, counter_amount
        received_asset, received_amount = base_asset, base_amount
        counterparty = raw.get("base_account")
    else:
        return None

    return NormalizedEvent(
        event_id=f"trade:{raw['id']}",
        account=account_id,
        timestamp=_parse_timestamp(raw["ledger_close_time"]),
        kind=EventKind.TRADE,
        asset=given_asset,
        amount=given_amount,
        counter_asset=received_asset,
        counter_amount=received_amount,
        counterparty=counterparty,
        source_operation_id=str(raw.get("base_offer_id") or raw["id"]),
    )


def normalize_claimable_balance_create(
    raw: dict[str, Any], account_id: str
) -> NormalizedEvent | None:
    """Normalize a ``create_claimable_balance`` operation. Unlike the claim
    side, the create operation carries its own asset/amount, so no effects
    lookup is needed.
    """
    if raw.get("source_account") != account_id:
        return None
    claimants = raw.get("claimants") or []
    counterparty = claimants[0]["destination"] if len(claimants) == 1 else None
    return NormalizedEvent(
        event_id=f"claimable_balance:{raw['id']}",
        account=account_id,
        timestamp=_parse_timestamp(raw["created_at"]),
        kind=EventKind.CLAIMABLE_BALANCE_CREATE,
        asset=_asset_from_canonical(raw["asset"]),
        amount=Decimal(raw["amount"]),
        counterparty=counterparty,
        source_operation_id=raw["id"],
    )


def normalize_claimable_balance_claim(
    raw: dict[str, Any], account_id: str, effects: list[dict[str, Any]]
) -> NormalizedEvent | None:
    """Normalize a ``claim_claimable_balance`` operation.

    The operation resource itself only carries ``claimant`` and
    ``balance_id`` — not the asset or amount claimed. That data lives on the
    operation's ``claimable_balance_claimed`` effect, so callers must fetch
    and pass in ``effects`` (see ``HorizonClient.get_operation_effects``).
    Returns ``None`` rather than a guessed amount if that effect is missing.
    """
    if raw.get("claimant") != account_id:
        return None
    claim_effect = next(
        (e for e in effects if e.get("type") == "claimable_balance_claimed"), None
    )
    if claim_effect is None:
        return None
    return NormalizedEvent(
        event_id=f"claimable_balance:{raw['id']}",
        account=account_id,
        timestamp=_parse_timestamp(raw["created_at"]),
        kind=EventKind.CLAIMABLE_BALANCE_CLAIM,
        asset=_asset_from_canonical(claim_effect["asset"]),
        amount=Decimal(claim_effect["amount"]),
        source_operation_id=raw["id"],
    )


_CLAIMABLE_BALANCE_OP_TYPES = frozenset(
    {"create_claimable_balance", "claim_claimable_balance"}
)


def normalize_account_activity(client: HorizonClient, account_id: str) -> list[NormalizedEvent]:
    """Fetch and normalize everything NairaTax currently understands for one
    account: payments/path payments, DEX trades, and claimable balance
    create/claim, merged into a single timestamp-ordered event stream.

    Operations this module can't safely normalize (e.g. ``account_merge``,
    or a claim whose ``claimable_balance_claimed`` effect is missing) are
    silently dropped by the underlying ``normalize_*`` functions rather than
    raising — a partial, honest event stream beats a hard failure on one
    unusual operation in an otherwise long history.
    """
    events: list[NormalizedEvent] = []

    for raw in client.iter_payments(account_id):
        event = normalize_payment(raw, account_id)
        if event is not None:
            events.append(event)

    for raw in client.iter_trades(account_id):
        event = normalize_trade(raw, account_id)
        if event is not None:
            events.append(event)

    for raw in client.iter_operations(account_id):
        op_type = raw.get("type")
        if op_type not in _CLAIMABLE_BALANCE_OP_TYPES:
            continue
        if op_type == "create_claimable_balance":
            event = normalize_claimable_balance_create(raw, account_id)
        else:
            effects = client.get_operation_effects(raw["id"])
            event = normalize_claimable_balance_claim(raw, account_id, effects)
        if event is not None:
            events.append(event)

    events.sort(key=lambda event: event.timestamp)
    return events
