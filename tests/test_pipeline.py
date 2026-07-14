from datetime import UTC, datetime

from nairatax.models import Classification
from nairatax.pipeline import run_report_pipeline
from nairatax.pricing import StaticPriceOracle

ACCOUNT_A = "GACCOUNTAXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX"
ACCOUNT_B = "GACCOUNTBXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX"
STRANGER = "GSTRANGERXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX"

PERIOD_START = datetime(2026, 1, 1, tzinfo=UTC)
PERIOD_END = datetime(2026, 12, 31, 23, 59, 59, tzinfo=UTC)


class _FakeHorizonClient:
    """Per-account fixture data, duck-typed like HorizonClient."""

    def __init__(self, payments_by_account=None):
        self._payments = payments_by_account or {}

    def iter_payments(self, account_id):
        return iter(self._payments.get(account_id, []))

    def iter_trades(self, account_id):
        return iter([])

    def iter_operations(self, account_id):
        return iter([])

    def get_operation_effects(self, operation_id):
        return []


def _payment(op_id, sender, recipient, amount="100", when="2026-02-01T00:00:00Z"):
    return {
        "id": op_id,
        "type": "payment",
        "created_at": when,
        "from": sender,
        "to": recipient,
        "asset_type": "native",
        "amount": amount,
    }


def test_pipeline_flags_external_inflow_as_needs_review():
    client = _FakeHorizonClient({ACCOUNT_A: [_payment("1", STRANGER, ACCOUNT_A)]})

    outcome = run_report_pipeline(
        ACCOUNT_A, "nigeria", PERIOD_START, PERIOD_END, client, StaticPriceOracle({})
    )

    assert len(outcome.needs_review) == 1
    assert outcome.needs_review[0].classification is Classification.NEEDS_REVIEW
    assert outcome.report.needs_review_count == 1
    assert outcome.report.line_items == []
    assert outcome.pack.jurisdiction == "nigeria"


def test_pipeline_recognises_self_transfer_between_own_accounts():
    client = _FakeHorizonClient(
        {
            ACCOUNT_A: [
                _payment("1", STRANGER, ACCOUNT_A, when="2026-02-01T00:00:00Z"),
                _payment("2", ACCOUNT_A, ACCOUNT_B, amount="40", when="2026-02-02T00:00:00Z"),
            ],
            ACCOUNT_B: [],
        }
    )

    outcome = run_report_pipeline(
        ACCOUNT_A,
        "nigeria",
        PERIOD_START,
        PERIOD_END,
        client,
        StaticPriceOracle({}),
        own_accounts=frozenset({ACCOUNT_B}),
    )

    # only the stranger inflow needs review; the A->B transfer is recognised
    # as a self-transfer and never reaches needs_review
    assert outcome.report.needs_review_count == 1
    assert outcome.needs_review[0].event.event_id == "payment:1"


def test_pipeline_without_own_accounts_treats_transfer_as_external():
    client = _FakeHorizonClient(
        {ACCOUNT_A: [_payment("2", ACCOUNT_A, ACCOUNT_B, amount="40")]}
    )

    outcome = run_report_pipeline(
        ACCOUNT_A, "nigeria", PERIOD_START, PERIOD_END, client, StaticPriceOracle({})
    )

    # ACCOUNT_B was never declared as owned, so this outflow needs review
    # like any other external transfer
    assert outcome.report.needs_review_count == 1


def test_pipeline_report_is_scoped_to_the_configured_period():
    client = _FakeHorizonClient(
        {ACCOUNT_A: [_payment("1", STRANGER, ACCOUNT_A, when="2025-06-01T00:00:00Z")]}
    )

    outcome = run_report_pipeline(
        ACCOUNT_A, "nigeria", PERIOD_START, PERIOD_END, client, StaticPriceOracle({})
    )

    assert outcome.report.period_start == PERIOD_START
    assert outcome.report.period_end == PERIOD_END
    assert outcome.report.line_items == []
