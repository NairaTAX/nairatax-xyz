"""``nairatax`` command-line interface."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from pathlib import Path

import typer

from nairatax import __version__
from nairatax.config import get_settings
from nairatax.ingestion.horizon_client import HorizonClient
from nairatax.pipeline import run_report_pipeline
from nairatax.pricing import StaticPriceOracle
from nairatax.reporting.export import to_csv, to_json

app = typer.Typer(
    name="nairatax",
    help="On-chain tax reporting for the Stellar ecosystem, starting with Nigeria.",
    add_completion=False,
)


class ReportFormat(StrEnum):
    json = "json"
    csv = "csv"


def _make_horizon_client(settings) -> HorizonClient:  # pragma: no cover - trivial factory
    """Real construction lives behind this seam so tests can substitute a
    client wired to a mock transport instead of touching the network.
    """
    return HorizonClient(settings)


def _parse_static_rates(price_options: list[str]) -> dict[str, Decimal]:
    rates: dict[str, Decimal] = {}
    for entry in price_options:
        if "=" not in entry:
            raise typer.BadParameter(f"expected ASSET=RATE, got {entry!r}")
        asset_id, _, rate_text = entry.partition("=")
        try:
            rates[asset_id] = Decimal(rate_text)
        except InvalidOperation as exc:
            raise typer.BadParameter(f"invalid rate {rate_text!r} for {asset_id!r}") from exc
    return rates


@app.command()
def version() -> None:
    """Print the installed nairatax version."""
    typer.echo(__version__)


@app.command()
def report(
    account: str = typer.Argument(..., help="Stellar account ID (G...) to report on."),
    year: int = typer.Option(..., "--year", help="Tax year, e.g. 2026."),
    jurisdiction: str = typer.Option(
        None, "--jurisdiction", help="Rule pack to apply. Defaults to NAIRATAX_JURISDICTION."
    ),
    own_account: list[str] = typer.Option(
        [],
        "--own-account",
        help="Another Stellar account you control (repeatable) — transfers to/from it are "
        "treated as self-transfers rather than needing review.",
    ),
    price: list[str] = typer.Option(
        [],
        "--price",
        help="Static FX rate ASSET=RATE (e.g. native=1500), repeatable. Demo/testing only — "
        "see nairatax.pricing — real historical pricing is not yet implemented.",
    ),
    output_format: ReportFormat = typer.Option(
        ReportFormat.json, "--format", help="Output format."
    ),
    output: Path = typer.Option(
        None, "--output", "-o", help="Write to this file instead of stdout."
    ),
) -> None:
    """Fetch, classify, and report on-chain activity for ACCOUNT."""
    settings = get_settings()
    resolved_jurisdiction = jurisdiction or settings.jurisdiction
    period_start = datetime(year, 1, 1, tzinfo=UTC)
    period_end = datetime(year, 12, 31, 23, 59, 59, tzinfo=UTC)
    price_oracle = StaticPriceOracle(_parse_static_rates(price))

    with _make_horizon_client(settings) as horizon_client:
        outcome = run_report_pipeline(
            account,
            resolved_jurisdiction,
            period_start,
            period_end,
            horizon_client,
            price_oracle,
            own_accounts=frozenset(own_account),
        )

    if not outcome.pack.verified:
        typer.secho(
            f"WARNING: rule pack {resolved_jurisdiction!r} is unverified — "
            f"{outcome.pack.source_note.strip()}",
            fg=typer.colors.YELLOW,
            err=True,
        )
    if outcome.needs_review:
        typer.secho(
            f"WARNING: {len(outcome.needs_review)} event(s) need manual review and are "
            "excluded from this report's totals.",
            fg=typer.colors.YELLOW,
            err=True,
        )

    rendered = to_json(outcome.report) if output_format is ReportFormat.json else to_csv(
        outcome.report
    )

    if output is not None:
        output.write_text(rendered)
        typer.echo(f"Wrote {output_format.value} report to {output}")
    else:
        typer.echo(rendered)


if __name__ == "__main__":  # pragma: no cover
    app()
