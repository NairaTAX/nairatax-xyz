import httpx
import pytest

from nairatax.config import Settings
from nairatax.ingestion.horizon_client import HorizonClient, HorizonError

BASE = "https://horizon-testnet.stellar.org"


def _settings() -> Settings:
    return Settings(horizon_url=BASE)


def _client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler), base_url=BASE)


def test_iter_payments_follows_pagination_cursor():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        if "cursor" not in request.url.params:
            return httpx.Response(
                200,
                json={
                    "_embedded": {"records": [{"id": "1", "type": "payment"}]},
                    "_links": {
                        "next": {
                            "href": f"{BASE}/accounts/GACC/payments?cursor=1&limit=200&order=asc"
                        }
                    },
                },
            )
        return httpx.Response(
            200,
            json={"_embedded": {"records": [{"id": "2", "type": "payment"}]}, "_links": {}},
        )

    horizon = HorizonClient(_settings(), client=_client(handler))
    records = list(horizon.iter_payments("GACC"))

    assert [r["id"] for r in records] == ["1", "2"]
    assert len(calls) == 2


def test_iter_payments_stops_when_no_next_link():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"_embedded": {"records": [{"id": "1"}]}, "_links": {}})

    horizon = HorizonClient(_settings(), client=_client(handler))
    assert len(list(horizon.iter_payments("GACC"))) == 1


def test_iter_stops_on_empty_page_even_with_a_next_link():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "_embedded": {"records": []},
                "_links": {"next": {"href": f"{BASE}/accounts/GACC/trades?cursor=999"}},
            },
        )

    horizon = HorizonClient(_settings(), client=_client(handler))
    assert list(horizon.iter_trades("GACC")) == []


def test_error_status_raises_horizon_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, text="account not found")

    horizon = HorizonClient(_settings(), client=_client(handler))
    with pytest.raises(HorizonError, match="404"):
        list(horizon.iter_payments("GMISSING"))


@pytest.mark.parametrize(
    ("method_name", "call_args", "expected_path"),
    [
        ("iter_payments", ("GACC",), "/accounts/GACC/payments"),
        ("iter_trades", ("GACC",), "/accounts/GACC/trades"),
        ("iter_operations", ("GACC",), "/accounts/GACC/operations"),
        ("get_operation_effects", ("op-1",), "/operations/op-1/effects"),
    ],
)
def test_each_method_hits_the_expected_path(method_name, call_args, expected_path):
    seen_paths = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_paths.append(request.url.path)
        return httpx.Response(200, json={"_embedded": {"records": []}, "_links": {}})

    horizon = HorizonClient(_settings(), client=_client(handler))
    list(getattr(horizon, method_name)(*call_args))

    assert seen_paths == [expected_path]


def test_context_manager_does_not_close_an_externally_supplied_client():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"_embedded": {"records": []}, "_links": {}})

    external_client = _client(handler)
    with HorizonClient(_settings(), client=external_client) as horizon:
        list(horizon.iter_trades("GACC"))

    assert not external_client.is_closed
