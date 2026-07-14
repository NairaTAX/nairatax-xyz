from decimal import Decimal

from nairatax.ingestion.normalize import normalize_payment
from nairatax.models import EventKind

ACCOUNT = "GACCOUNTOWNERXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX"
OTHER = "GOTHERACCOUNTXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX"
USDC_ISSUER = "GA5ZSEJYB37JRC5AVCIA5MOP4RHTM335X2KGX3IHOJAPP5RE34K4KZVN"


def test_payment_out():
    raw = {
        "id": "1",
        "type": "payment",
        "created_at": "2026-03-01T12:00:00Z",
        "from": ACCOUNT,
        "to": OTHER,
        "asset_type": "native",
        "amount": "10.5000000",
    }
    event = normalize_payment(raw, ACCOUNT)
    assert event.kind is EventKind.PAYMENT_OUT
    assert event.asset.id == "native"
    assert event.amount == Decimal("10.5000000")
    assert event.counterparty == OTHER


def test_payment_in_issued_asset():
    raw = {
        "id": "2",
        "type": "payment",
        "created_at": "2026-03-01T12:00:00Z",
        "from": OTHER,
        "to": ACCOUNT,
        "asset_type": "credit_alphanum4",
        "asset_code": "USDC",
        "asset_issuer": USDC_ISSUER,
        "amount": "100.0000000",
    }
    event = normalize_payment(raw, ACCOUNT)
    assert event.kind is EventKind.PAYMENT_IN
    assert event.asset.code == "USDC"
    assert event.counterparty == OTHER


def test_payment_not_involving_account_is_skipped():
    raw = {
        "id": "3",
        "type": "payment",
        "created_at": "2026-03-01T12:00:00Z",
        "from": OTHER,
        "to": "GSOMEONEELSEXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX",
        "asset_type": "native",
        "amount": "1",
    }
    assert normalize_payment(raw, ACCOUNT) is None


def test_self_path_payment_is_a_swap():
    raw = {
        "id": "4",
        "type": "path_payment_strict_send",
        "created_at": "2026-03-01T12:00:00Z",
        "from": ACCOUNT,
        "to": ACCOUNT,
        "asset_type": "credit_alphanum4",
        "asset_code": "USDC",
        "asset_issuer": USDC_ISSUER,
        "amount": "98.5000000",
        "source_asset_type": "native",
        "source_amount": "100.0000000",
    }
    event = normalize_payment(raw, ACCOUNT)
    assert event.kind is EventKind.PATH_PAYMENT_OUT
    assert event.asset.id == "native"
    assert event.amount == Decimal("100.0000000")
    assert event.counter_asset.code == "USDC"
    assert event.counter_amount == Decimal("98.5000000")
    assert event.counterparty == ACCOUNT


def test_path_payment_as_sender_to_third_party():
    raw = {
        "id": "5",
        "type": "path_payment_strict_receive",
        "created_at": "2026-03-01T12:00:00Z",
        "from": ACCOUNT,
        "to": OTHER,
        "asset_type": "native",
        "amount": "50.0000000",
        "source_asset_type": "credit_alphanum4",
        "source_asset_code": "USDC",
        "source_asset_issuer": USDC_ISSUER,
        "source_amount": "51.0000000",
    }
    event = normalize_payment(raw, ACCOUNT)
    assert event.kind is EventKind.PATH_PAYMENT_OUT
    assert event.asset.code == "USDC"
    assert event.amount == Decimal("51.0000000")
    assert event.counter_asset is None
    assert event.counterparty == OTHER


def test_path_payment_as_recipient():
    raw = {
        "id": "6",
        "type": "path_payment_strict_receive",
        "created_at": "2026-03-01T12:00:00Z",
        "from": OTHER,
        "to": ACCOUNT,
        "asset_type": "native",
        "amount": "50.0000000",
        "source_asset_type": "credit_alphanum4",
        "source_asset_code": "USDC",
        "source_asset_issuer": USDC_ISSUER,
        "source_amount": "51.0000000",
    }
    event = normalize_payment(raw, ACCOUNT)
    assert event.kind is EventKind.PATH_PAYMENT_IN
    assert event.asset.id == "native"
    assert event.amount == Decimal("50.0000000")
    assert event.counterparty == OTHER


def test_create_account_as_funder():
    raw = {
        "id": "7",
        "type": "create_account",
        "created_at": "2026-03-01T12:00:00Z",
        "funder": ACCOUNT,
        "account": OTHER,
        "starting_balance": "25.0000000",
    }
    event = normalize_payment(raw, ACCOUNT)
    assert event.kind is EventKind.PAYMENT_OUT
    assert event.asset.id == "native"
    assert event.amount == Decimal("25.0000000")
    assert event.counterparty == OTHER


def test_create_account_as_new_account():
    raw = {
        "id": "8",
        "type": "create_account",
        "created_at": "2026-03-01T12:00:00Z",
        "funder": OTHER,
        "account": ACCOUNT,
        "starting_balance": "25.0000000",
    }
    event = normalize_payment(raw, ACCOUNT)
    assert event.kind is EventKind.PAYMENT_IN
    assert event.counterparty == OTHER


def test_account_merge_is_skipped_rather_than_guessed():
    raw = {
        "id": "9",
        "type": "account_merge",
        "created_at": "2026-03-01T12:00:00Z",
        "account": ACCOUNT,
        "into": OTHER,
    }
    assert normalize_payment(raw, ACCOUNT) is None
