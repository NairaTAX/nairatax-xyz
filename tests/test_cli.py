import json

import httpx
import pytest
from typer.testing import CliRunner

import nairatax.cli as cli_module
from nairatax import __version__
from nairatax.cli import app
from nairatax.config import Settings
from nairatax.ingestion.horizon_client import HorizonClient

runner = CliRunner()

ACCOUNT = "GACCOUNTXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX"


def _empty_horizon_client() -> HorizonClient:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"_embedded": {"records": []}, "_links": {}})

    transport_client = httpx.Client(
        transport=httpx.MockTransport(handler), base_url="https://horizon-testnet.stellar.org"
    )
    return HorizonClient(Settings(), client=transport_client)


@pytest.fixture
def no_network(monkeypatch):
    """Substitute the CLI's Horizon client factory with one wired to a mock
    transport that always returns empty pages, so `report` can run without
    touching the network.
    """
    monkeypatch.setattr(
        cli_module, "_make_horizon_client", lambda settings: _empty_horizon_client()
    )


def test_version_command_prints_the_package_version():
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert result.output.strip() == __version__


def test_report_with_no_activity_produces_an_empty_report(no_network):
    result = runner.invoke(app, ["report", ACCOUNT, "--year", "2026"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert payload["account"] == ACCOUNT
    assert payload["jurisdiction"] == "nigeria"
    assert payload["line_items"] == []


def test_report_warns_about_unverified_rule_pack(no_network):
    result = runner.invoke(app, ["report", ACCOUNT, "--year", "2026"])
    assert "unverified" in result.output.lower()


def test_report_csv_format_outputs_a_header_row(no_network):
    result = runner.invoke(app, ["report", ACCOUNT, "--year", "2026", "--format", "csv"])

    assert result.exit_code == 0, result.output
    assert result.stdout.splitlines()[0].startswith("date,category,asset")


def test_report_writes_to_output_file(no_network, tmp_path):
    out_file = tmp_path / "report.json"

    result = runner.invoke(app, ["report", ACCOUNT, "--year", "2026", "--output", str(out_file)])

    assert result.exit_code == 0, result.output
    assert out_file.exists()
    payload = json.loads(out_file.read_text())
    assert payload["account"] == ACCOUNT


def test_report_rejects_malformed_price_option(no_network):
    result = runner.invoke(
        app, ["report", ACCOUNT, "--year", "2026", "--price", "not-a-valid-entry"]
    )

    assert result.exit_code != 0
    assert "ASSET=RATE" in result.output
