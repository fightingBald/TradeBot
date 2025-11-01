import json
import os
from datetime import date
from types import SimpleNamespace
from pathlib import Path

import pytest

from data_sources.earnings_to_calendar import (
    DEFAULT_LOOKAHEAD_DAYS,
    EarningsEvent,
    FmpEarningsProvider,
    FinnhubEarningsProvider,
    RuntimeOptions,
    build_ics,
    deduplicate_events,
    _parse_symbols,
)
from data_sources.earnings_to_calendar.cli import (
    _build_runtime_options,
    _load_config,
    _load_env_file,
)


class StubResponse:
    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload

    def raise_for_status(self):
        return None


def test_fmp_provider_filters_and_normalizes():
    payload = [
        {"symbol": "aapl", "date": "2024-01-25", "time": "AMC"},
        {"symbol": "msft", "earningsDate": "2024-01-30"},
        {"symbol": "tsla", "date": "bad-date"},
    ]

    captured: dict[str, str] = {}

    def fake_get(url, **kwargs):
        captured["url"] = url
        captured["user_agent"] = kwargs["headers"]["User-Agent"]
        return StubResponse(payload)

    provider = FmpEarningsProvider("token", http_get=fake_get)
    events = provider.fetch(["AAPL", "MSFT"], date(2024, 1, 1), date(2024, 1, 31))

    assert captured["user_agent"] == "earnings-to-calendar/1.0"
    assert "from=2024-01-01" in captured["url"]
    assert "to=2024-01-31" in captured["url"]
    assert len(events) == 2
    assert events[0] == EarningsEvent("AAPL", date(2024, 1, 25), "AMC", "FMP")
    assert events[1] == EarningsEvent("MSFT", date(2024, 1, 30), "", "FMP")


def test_finnhub_provider_handles_nested_payload():
    payload = {
        "earningsCalendar": [
            {"symbol": "AAPL", "date": "2024-01-25", "hour": "bmo"},
            {"symbol": "GOOGL", "date": None},
        ]
    }

    def fake_get(url, **kwargs):
        return StubResponse(payload)

    provider = FinnhubEarningsProvider("token", http_get=fake_get)
    events = provider.fetch(["AAPL", "GOOGL"], date(2024, 1, 1), date(2024, 1, 31))

    assert events == [
        EarningsEvent("AAPL", date(2024, 1, 25), "BMO", "Finnhub"),
    ]


def test_deduplicate_events_preserves_first_occurrence():
    first = EarningsEvent("AAPL", date(2024, 1, 10), "BMO", "FMP")
    duplicate = EarningsEvent("AAPL", date(2024, 1, 10), "AMC", "Finnhub")
    other = EarningsEvent("MSFT", date(2024, 1, 12), "", "FMP")

    deduped = deduplicate_events([first, duplicate, other])

    assert deduped == [first, other]


def test_build_ics_generates_expected_fields():
    event = EarningsEvent("AAPL", date(2024, 1, 25), "AMC", "FMP", url="https://example.com")
    ics = build_ics([event], prodid="-//test//")

    assert "PRODID:-//test//" in ics
    assert "SUMMARY:AAPL Earnings (AMC)" in ics
    assert "DESCRIPTION:Earnings date from FMP." in ics
    assert "URL:https://example.com" in ics


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("AAPL, msft, AAPL", ["AAPL", "MSFT"]),
        ("  , ,", []),
        ("TSLA", ["TSLA"]),
    ],
)
def test_parse_symbols_normalizes_and_deduplicates(raw, expected):
    assert _parse_symbols(raw.split(",")) == expected


def test_load_env_file_populates_environment(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text("NEW_VAR=value\nEXISTING=should_not_override\n", encoding="utf-8")
    monkeypatch.setenv("EXISTING", "keep")
    monkeypatch.delenv("NEW_VAR", raising=False)

    _load_env_file(str(env_file))

    assert os.environ["NEW_VAR"] == "value"
    assert os.environ["EXISTING"] == "keep"


def test_load_env_file_falls_back_to_search_root(tmp_path, monkeypatch):
    env_file = tmp_path / "fallback.env"
    env_file.write_text("FALLBACK_VAR=from_root\n", encoding="utf-8")
    monkeypatch.delenv("FALLBACK_VAR", raising=False)

    _load_env_file("fallback.env", search_root=tmp_path)

    assert os.environ["FALLBACK_VAR"] == "from_root"


def test_load_config_reads_json(tmp_path):
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({"symbols": ["AAPL"]}), encoding="utf-8")

    config, base = _load_config(str(config_path))

    assert base == config_path.parent
    assert config["symbols"] == ["AAPL"]


def test_build_runtime_options_merges_config(tmp_path, monkeypatch):
    for key in [
        "GOOGLE_CREDENTIALS_PATH",
        "GOOGLE_TOKEN_PATH",
        "GOOGLE_INSERT",
        "ICLOUD_INSERT",
        "ICLOUD_APPLE_ID",
        "ICLOUD_APP_PASSWORD",
    ]:
        monkeypatch.delenv(key, raising=False)

    config = {
        "symbols": ["AAPL", "MSFT"],
        "source": "finnhub",
        "days": "45",
        "export_ics": "out.ics",
        "google_insert": True,
        "google_credentials": "cfg_creds.json",
        "google_token": "cfg_token.json",
        "icloud_insert": True,
        "icloud_id": "user@icloud.com",
        "icloud_app_pass": "abcd-efgh",
    }

    parsed = SimpleNamespace(
        symbols=None,
        source=None,
        days=None,
        export_ics=None,
        google_insert=False,
        google_credentials=None,
        google_token=None,
        icloud_insert=False,
        icloud_id=None,
        icloud_app_pass=None,
    )

    project_root = Path(tmp_path)

    options = _build_runtime_options(
        parsed,
        config,
        config_base=None,
        project_root=project_root,
    )

    assert isinstance(options, RuntimeOptions)
    assert options.symbols == ["AAPL", "MSFT"]
    assert options.source == "finnhub"
    assert options.days == 45
    assert options.export_ics == "out.ics"
    assert options.google_insert is True
    assert options.google_credentials == str(project_root / "cfg_creds.json")
    assert options.google_token == str(project_root / "cfg_token.json")
    assert options.icloud_insert is True
    assert options.icloud_id == "user@icloud.com"
    assert options.icloud_app_pass == "abcd-efgh"


def test_build_runtime_options_cli_overrides_config(tmp_path, monkeypatch):
    for key in [
        "GOOGLE_CREDENTIALS_PATH",
        "GOOGLE_TOKEN_PATH",
        "GOOGLE_INSERT",
        "ICLOUD_INSERT",
        "ICLOUD_APPLE_ID",
        "ICLOUD_APP_PASSWORD",
    ]:
        monkeypatch.delenv(key, raising=False)

    config = {
        "symbols": ["AAPL"],
        "source": "finnhub",
        "days": 30,
        "google_credentials": "cfg.json",
    }

    parsed = SimpleNamespace(
        symbols="TSLA, msft",
        source="fmp",
        days=10,
        export_ics=None,
        google_insert=True,
        google_credentials="cli_creds.json",
        google_token=None,
        icloud_insert=False,
        icloud_id=None,
        icloud_app_pass=None,
    )

    project_root = Path(tmp_path)

    options = _build_runtime_options(
        parsed,
        config,
        config_base=None,
        project_root=project_root,
    )

    assert options.symbols == ["TSLA", "MSFT"]
    assert options.source == "fmp"
    assert options.days == 10
    assert options.google_credentials == str(project_root / "cli_creds.json")
    assert options.google_insert is True


def test_build_runtime_options_uses_env_defaults(tmp_path, monkeypatch):
    monkeypatch.delenv("GOOGLE_CREDENTIALS_PATH", raising=False)
    monkeypatch.delenv("GOOGLE_TOKEN_PATH", raising=False)
    monkeypatch.delenv("GOOGLE_INSERT", raising=False)
    monkeypatch.delenv("ICLOUD_INSERT", raising=False)
    monkeypatch.delenv("ICLOUD_APPLE_ID", raising=False)
    monkeypatch.delenv("ICLOUD_APP_PASSWORD", raising=False)

    monkeypatch.setenv("GOOGLE_CREDENTIALS_PATH", "/secrets/credentials.json")
    monkeypatch.setenv("GOOGLE_TOKEN_PATH", "/secrets/token.json")
    monkeypatch.setenv("GOOGLE_INSERT", "true")
    monkeypatch.setenv("ICLOUD_INSERT", "1")
    monkeypatch.setenv("ICLOUD_APPLE_ID", "user@icloud.com")
    monkeypatch.setenv("ICLOUD_APP_PASSWORD", "pass-1234")

    parsed = SimpleNamespace(
        symbols="TSLA",
        source=None,
        days=None,
        export_ics=None,
        google_insert=False,
        google_credentials=None,
        google_token=None,
        icloud_insert=False,
        icloud_id=None,
        icloud_app_pass=None,
    )

    config_base = Path(tmp_path) / "config_dir"
    config_base.mkdir()

    options = _build_runtime_options(
        parsed,
        {},
        config_base=config_base,
        project_root=Path(tmp_path),
    )

    assert options.symbols == ["TSLA"]
    assert options.source == "fmp"
    assert options.days == DEFAULT_LOOKAHEAD_DAYS
    assert options.google_credentials == str(Path("/secrets/credentials.json"))
    assert options.google_token == str(Path("/secrets/token.json"))
    assert options.google_insert is True
    assert options.icloud_insert is True
    assert options.icloud_id == "user@icloud.com"
    assert options.icloud_app_pass == "pass-1234"


def test_build_runtime_options_resolves_paths_relative_to_config(tmp_path, monkeypatch):
    config_base = tmp_path / "cfg"
    config_base.mkdir()
    secrets_dir = config_base / "secrets"
    secrets_dir.mkdir()

    config = {
        "symbols": ["AAPL"],
        "google_credentials": "secrets/credentials.json",
        "google_token": "secrets/token.json",
    }

    parsed = SimpleNamespace(
        symbols=None,
        source=None,
        days=None,
        export_ics=None,
        google_insert=False,
        google_credentials=None,
        google_token=None,
        icloud_insert=False,
        icloud_id=None,
        icloud_app_pass=None,
    )

    options = _build_runtime_options(
        parsed,
        config,
        config_base=config_base,
        project_root=tmp_path,
    )

    assert options.google_credentials == str(config_base / "secrets/credentials.json")
    assert options.google_token == str(config_base / "secrets/token.json")
