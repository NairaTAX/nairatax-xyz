from decimal import Decimal

from nairatax.ingestion.normalize import (
    normalize_account_activity,
    normalize_claimable_balance_claim,
    normalize_claimable_balance_create,
    normalize_payment,
    normalize_trade,
)
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


def _trade_raw(**overrides) -> dict:
    raw = {
        "id": "trade-1",
        "ledger_close_time": "2026-04-01T09:30:00Z",
        "base_account": ACCOUNT,
        "base_asset_type": "native",
        "base_amount": "100.0000000",
        "base_is_seller": True,
        "counter_account": OTHER,
        "counter_asset_type": "credit_alphanum4",
        "counter_asset_code": "USDC",
        "counter_asset_issuer": USDC_ISSUER,
        "counter_amount": "98.0000000",
        "base_offer_id": "555",
    }
    raw.update(overrides)
    return raw


def test_trade_as_base_account_gives_base_receives_counter():
    event = normalize_trade(_trade_raw(), ACCOUNT)
    assert event.kind is EventKind.TRADE
    assert event.asset.id == "native"
    assert event.amount == Decimal("100.0000000")
    assert event.counter_asset.code == "USDC"
    assert event.counter_amount == Decimal("98.0000000")
    assert event.counterparty == OTHER


def test_trade_as_counter_account_gives_counter_receives_base():
    event = normalize_trade(_trade_raw(base_is_seller=False), OTHER)
    assert event.asset.code == "USDC"
    assert event.amount == Decimal("98.0000000")
    assert event.counter_asset.id == "native"
    assert event.counter_amount == Decimal("100.0000000")
    assert event.counterparty == ACCOUNT


def test_trade_direction_is_unaffected_by_base_is_seller_flag():
    as_seller = normalize_trade(_trade_raw(base_is_seller=True), ACCOUNT)
    as_buyer = normalize_trade(_trade_raw(base_is_seller=False), ACCOUNT)
    assert as_seller.asset == as_buyer.asset
    assert as_seller.amount == as_buyer.amount


def test_trade_not_involving_account_is_skipped():
    unrelated = "GUNRELATEDXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX"
    assert normalize_trade(_trade_raw(), unrelated) is None


def test_claimable_balance_create_single_claimant():
    raw = {
        "id": "10",
        "type": "create_claimable_balance",
        "created_at": "2026-05-01T00:00:00Z",
        "source_account": ACCOUNT,
        "asset": "native",
        "amount": "40.0000000",
        "claimants": [{"destination": OTHER, "predicate": {"unconditional": True}}],
    }
    event = normalize_claimable_balance_create(raw, ACCOUNT)
    assert event.kind is EventKind.CLAIMABLE_BALANCE_CREATE
    assert event.asset.id == "native"
    assert event.amount == Decimal("40.0000000")
    assert event.counterparty == OTHER


def test_claimable_balance_create_issued_asset_canonical_form():
    raw = {
        "id": "11",
        "type": "create_claimable_balance",
        "created_at": "2026-05-01T00:00:00Z",
        "source_account": ACCOUNT,
        "asset": f"USDC:{USDC_ISSUER}",
        "amount": "10.0000000",
        "claimants": [{"destination": OTHER}],
    }
    event = normalize_claimable_balance_create(raw, ACCOUNT)
    assert event.asset.code == "USDC"
    assert event.asset.issuer == USDC_ISSUER


def test_claimable_balance_create_by_someone_else_is_skipped():
    raw = {
        "id": "12",
        "type": "create_claimable_balance",
        "created_at": "2026-05-01T00:00:00Z",
        "source_account": OTHER,
        "asset": "native",
        "amount": "1",
        "claimants": [{"destination": ACCOUNT}],
    }
    assert normalize_claimable_balance_create(raw, ACCOUNT) is None


def test_claimable_balance_claim_resolves_amount_from_effect():
    raw = {
        "id": "13",
        "type": "claim_claimable_balance",
        "created_at": "2026-06-01T00:00:00Z",
        "claimant": ACCOUNT,
        "balance_id": "00000000abc",
    }
    effects = [
        {"type": "account_credited", "asset_type": "native"},
        {"type": "claimable_balance_claimed", "asset": "native", "amount": "40.0000000"},
    ]
    event = normalize_claimable_balance_claim(raw, ACCOUNT, effects)
    assert event.kind is EventKind.CLAIMABLE_BALANCE_CLAIM
    assert event.asset.id == "native"
    assert event.amount == Decimal("40.0000000")


def test_claimable_balance_claim_without_effect_is_skipped_not_guessed():
    raw = {
        "id": "14",
        "type": "claim_claimable_balance",
        "created_at": "2026-06-01T00:00:00Z",
        "claimant": ACCOUNT,
        "balance_id": "00000000abc",
    }
    assert normalize_claimable_balance_claim(raw, ACCOUNT, effects=[]) is None


def test_claimable_balance_claim_by_someone_else_is_skipped():
    raw = {
        "id": "15",
        "type": "claim_claimable_balance",
        "created_at": "2026-06-01T00:00:00Z",
        "claimant": OTHER,
        "balance_id": "00000000abc",
    }
    effects = [{"type": "claimable_balance_claimed", "asset": "native", "amount": "1"}]
    assert normalize_claimable_balance_claim(raw, ACCOUNT, effects) is None


class _FakeHorizonClient:
    """Duck-typed stand-in for HorizonClient — the orchestrator only calls
    these four methods, so a real HTTP mock would be pure overhead here.
    """

    def __init__(self, payments=(), trades=(), operations=(), effects_by_op=None):
        self._payments = list(payments)
        self._trades = list(trades)
        self._operations = list(operations)
        self._effects_by_op = effects_by_op or {}

    def iter_payments(self, account_id):
        return iter(self._payments)

    def iter_trades(self, account_id):
        return iter(self._trades)

    def iter_operations(self, account_id):
        return iter(self._operations)

    def get_operation_effects(self, operation_id):
        return self._effects_by_op.get(operation_id, [])


def test_normalize_account_activity_merges_and_sorts_by_time():
    payment = {
        "id": "1",
        "type": "payment",
        "created_at": "2026-03-03T00:00:00Z",
        "from": OTHER,
        "to": ACCOUNT,
        "asset_type": "native",
        "amount": "1",
    }
    trade = _trade_raw(ledger_close_time="2026-03-01T00:00:00Z")
    claim_op = {
        "id": "13",
        "type": "claim_claimable_balance",
        "created_at": "2026-03-02T00:00:00Z",
        "claimant": ACCOUNT,
        "balance_id": "bal-1",
    }
    create_op = {
        "id": "16",
        "type": "create_claimable_balance",
        "created_at": "2026-03-04T00:00:00Z",
        "source_account": ACCOUNT,
        "asset": "native",
        "amount": "20.0000000",
        "claimants": [{"destination": OTHER}],
    }
    unrelated_op = {"id": "99", "type": "manage_sell_offer", "created_at": "2026-03-02T00:00:00Z"}

    client = _FakeHorizonClient(
        payments=[payment],
        trades=[trade],
        operations=[claim_op, create_op, unrelated_op],
        effects_by_op={
            "13": [{"type": "claimable_balance_claimed", "asset": "native", "amount": "5"}]
        },
    )

    events = normalize_account_activity(client, ACCOUNT)

    assert [e.timestamp for e in events] == sorted(e.timestamp for e in events)
    assert len(events) == 4
    kinds = {e.kind for e in events}
    assert kinds == {
        EventKind.TRADE,
        EventKind.CLAIMABLE_BALANCE_CLAIM,
        EventKind.CLAIMABLE_BALANCE_CREATE,
        EventKind.PAYMENT_IN,
    }


def test_normalize_account_activity_with_no_activity_is_empty():
    client = _FakeHorizonClient()
    assert normalize_account_activity(client, ACCOUNT) == []
