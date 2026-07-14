"""Turn raw Horizon JSON records into :class:`NormalizedEvent` objects.

Each ``normalize_*`` function is a pure function over one raw record plus the
account being processed — no I/O — so they're trivial to unit test with
fixture dicts. :func:`normalize_account_activity` is the only function here
that talks to a :class:`HorizonClient`.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from nairatax.models import Asset, EventKind, NormalizedEvent


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
