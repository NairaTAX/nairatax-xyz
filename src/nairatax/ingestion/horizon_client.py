"""Thin, paginating HTTP client for the Stellar Horizon API.

Deliberately does not depend on stellar-sdk's synchronous CallBuilder
network layer: Horizon pagination is a plain HAL cursor (``_links.next.href``),
and a minimal client here keeps the ingestion path easy to test by injecting
an ``httpx.MockTransport`` instead of mocking into a third-party SDK.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import httpx

from nairatax.config import Settings


class HorizonError(RuntimeError):
    """Raised when Horizon returns a non-2xx response."""


class HorizonClient:
    """Read-only client for the account-scoped Horizon endpoints NairaTax needs.

    ``client`` can be supplied in tests as an ``httpx.Client`` built on
    ``httpx.MockTransport`` so no real network call ever happens off testnet.
    """

    def __init__(self, settings: Settings, client: httpx.Client | None = None) -> None:
        self._page_limit = settings.horizon_page_limit
        self._owns_client = client is None
        self._client = client or httpx.Client(
            base_url=settings.horizon_url.rstrip("/"),
            timeout=settings.horizon_request_timeout_seconds,
        )

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> HorizonClient:
        return self

    def __exit__(self, *_exc_info: object) -> None:
        self.close()

    def _paginate(self, path: str, params: dict[str, Any]) -> Iterator[dict[str, Any]]:
        url: str = path
        query: dict[str, Any] | None = {**params, "limit": self._page_limit, "order": "asc"}
        while True:
            response = self._client.get(url, params=query)
            if response.status_code >= 400:
                raise HorizonError(
                    f"Horizon {response.status_code} for {response.url}: {response.text[:300]}"
                )
            payload = response.json()
            records: list[dict[str, Any]] = payload.get("_embedded", {}).get("records", [])
            yield from records
            if not records:
                return
            next_href = payload.get("_links", {}).get("next", {}).get("href")
            if not next_href:
                return
            # next_href already carries the cursor querystring; use it verbatim
            # and stop merging in the original params.
            url = next_href
            query = None

    def iter_payments(self, account_id: str) -> Iterator[dict[str, Any]]:
        """Payment-shaped operations for ``account_id``: payment,
        path_payment_strict_send/receive, create_account, account_merge.
        """
        yield from self._paginate(
            f"/accounts/{account_id}/payments", {"include_failed": "false"}
        )

    def iter_trades(self, account_id: str) -> Iterator[dict[str, Any]]:
        """Executed DEX fills where ``account_id`` was either side of the trade."""
        yield from self._paginate(f"/accounts/{account_id}/trades", {})

    def iter_operations(self, account_id: str) -> Iterator[dict[str, Any]]:
        """All operations for ``account_id``. Horizon has no server-side type
        filter on this endpoint, so callers filter client-side (used here to
        pull out claimable-balance operations).
        """
        yield from self._paginate(
            f"/accounts/{account_id}/operations", {"include_failed": "false"}
        )

    def get_operation_effects(self, operation_id: str) -> list[dict[str, Any]]:
        """Effects for a single operation. Used to resolve the asset/amount of
        a ``claim_claimable_balance`` operation, which — unlike
        ``create_claimable_balance`` — does not carry that data on the
        operation record itself; the ``claimable_balance_claimed`` effect does.
        """
        return list(self._paginate(f"/operations/{operation_id}/effects", {}))
