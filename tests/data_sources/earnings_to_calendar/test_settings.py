import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from toolkits.calendar_svc import (
    DEFAULT_EVENT_DURATION_MINUTES, DEFAULT_LOOKAHEAD_DAYS,
    DEFAULT_SESSION_TIMES, DEFAULT_SOURCE_TIMEZONE, DEFAULT_TARGET_TIMEZONE)
from toolkits.calendar_svc import (RuntimeOptions,
                                   build_runtime_options, load_config,
                                   load_env_file, parse_symbols)


def test_parse_symbols_normalizes_and_deduplicates():
    assert parse_symbols("AAPL, msft, AAPL".split(",")) == ["AAPL", "MSFT"]
    assert parse_symbols("  , ,".split(",")) == []
    assert parse_symbols(["TSLA"]) == ["TSLA"]


def test_load_env_file_populates_environment(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "NEW_VAR=value\nEXISTING=should_not_override\n", encoding="utf-8"
    )
    monkeypatch.setenv("EXISTING", "keep")
    monkeypatch.delenv("NEW_VAR", raising=False)

    load_env_file(str(env_file))

    assert os.environ["NEW_VAR"] == "value"
    assert os.environ["EXISTING"] == "keep"


def test_load_env_file_falls_back_to_search_root(tmp_path, monkeypatch):
    env_file = tmp_path / "fallback.env"
    env_file.write_text("FALLBACK_VAR=from_root\n", encoding="utf-8")
    monkeypatch.delenv("FALLBACK_VAR", raising=False)

    load_env_file("fallback.env", search_root=tmp_path)

    assert os.environ["FALLBACK_VAR"] == "from_root"


def test_load_config_reads_json(tmp_path):
    config_path = tmp_path / "config.json"
    config_path.write_text(json.dumps({"symbols": ["AAPL"]}), encoding="utf-8")

    config, base = load_config(str(config_path), default_path=None)

    assert base == config_path.parent
    assert config["symbols"] == ["AAPL"]


def test_load_config_defaults_to_toml(tmp_path):
    default_path = tmp_path / "config" / "events_to_google_calendar.toml"
    default_path.parent.mkdir()
    default_path.write_text('symbols = ["TSLA"]\n', encoding="utf-8")

    config, base = load_config(None, default_path=default_path)

    assert base == default_path.parent
    assert config["symbols"] == ["TSLA"]


def _clear_env(monkeypatch):
    for key in [
        "GOOGLE_CREDENTIALS_PATH",
        "GOOGLE_TOKEN_PATH",
        "GOOGLE_INSERT",
        "GOOGLE_CALENDAR_ID",
        "GOOGLE_CALENDAR_NAME",
        "GOOGLE_CREATE_CALENDAR",
        "MARKET_EVENTS",
        "SOURCE_TIMEZONE",
        "TARGET_TIMEZONE",
        "EVENT_DURATION_MINUTES",
        "SESSION_TIMES",
        "ICLOUD_INSERT",
        "ICLOUD_APPLE_ID",
        "ICLOUD_APP_PASSWORD",
        "MACRO_EVENTS",
        "MACRO_EVENT_KEYWORDS",
        "MACRO_EVENT_SOURCE",
        "INCREMENTAL_SYNC",
        "SYNC_STATE_PATH",
    ]:
        monkeypatch.delenv(key, raising=False)


def test_build_runtime_options_merges_config(tmp_path, monkeypatch):
    _clear_env(monkeypatch)

    config = {
        "symbols": ["AAPL", "MSFT"],
        "source": "finnhub",
        "days": "45",
        "export_ics": "out.ics",
        "google_insert": True,
        "google_credentials": "cfg_creds.json",
        "google_token": "cfg_token.json",
        "google_calendar_name": "Company Earnings",
        "google_create_calendar": True,
        "source_timezone": "America/New_York",
        "target_timezone": "Europe/Berlin",
        "event_duration_minutes": "90",
        "session_times": {"BMO": "07:30", "AMC": "18:45"},
        "market_events": True,
        "icloud_insert": True,
        "icloud_id": "user@icloud.com",
        "icloud_app_pass": "abcd-efgh",
        "macro_events": True,
        "macro_event_keywords": ["FOMC", "CPI"],
        "macro_event_source": "benzinga",
    }

    parsed = SimpleNamespace(
        symbols=None,
        source=None,
        days=None,
        export_ics=None,
        google_insert=False,
        google_credentials=None,
        google_token=None,
        google_calendar_id=None,
        google_calendar_name=None,
        google_create_calendar=False,
        source_tz=None,
        target_tz=None,
        event_duration=None,
        session_times=None,
        market_events=False,
        icloud_insert=False,
        icloud_id=None,
        icloud_app_pass=None,
        macro_events=False,
        macro_event_keywords=None,
        macro_event_source=None,
        incremental=False,
        sync_state_path=None,
    )

    project_root = Path(tmp_path)

    options = build_runtime_options(
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
    assert options.google_calendar_id is None
    assert options.google_calendar_name == "Company Earnings"
    assert options.google_create_calendar is True
    assert options.source_timezone == "America/New_York"
    assert options.target_timezone == "Europe/Berlin"
    assert options.event_duration_minutes == 90
    assert options.session_time_map == {"BMO": "07:30", "AMC": "18:45"}
    assert options.icloud_insert is True
    assert options.icloud_id == "user@icloud.com"
    assert options.icloud_app_pass == "abcd-efgh"
    assert options.market_events is True
    assert options.macro_events is True
    assert options.macro_event_keywords == ["FOMC", "CPI"]
    assert options.macro_event_source == "benzinga"
    assert options.incremental_sync is False
    assert options.sync_state_path is None


def test_build_runtime_options_cli_overrides_config(tmp_path, monkeypatch):
    _clear_env(monkeypatch)

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
        google_calendar_id="custom-id",
        google_calendar_name=None,
        google_create_calendar=True,
        source_tz="America/Chicago",
        target_tz=None,
        event_duration=None,
        session_times=None,
        market_events=True,
        icloud_insert=False,
        icloud_id=None,
        icloud_app_pass=None,
        macro_events=True,
        macro_event_keywords="Treasury",
        macro_event_source="benzinga",
        incremental=True,
        sync_state_path="state.json",
    )

    project_root = Path(tmp_path)

    options = build_runtime_options(
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
    assert options.google_calendar_id == "custom-id"
    assert options.google_calendar_name is None
    assert options.google_create_calendar is True
    assert options.source_timezone == "America/Chicago"
    assert options.target_timezone == DEFAULT_TARGET_TIMEZONE
    assert options.event_duration_minutes == DEFAULT_EVENT_DURATION_MINUTES
    assert options.session_time_map == DEFAULT_SESSION_TIMES
    assert options.market_events is True
    assert options.macro_events is True
    assert options.macro_event_keywords == ["Treasury"]
    assert options.macro_event_source == "benzinga"
    assert options.incremental_sync is True
    assert options.sync_state_path.endswith("state.json")


def test_build_runtime_options_uses_env_defaults(tmp_path, monkeypatch):
    _clear_env(monkeypatch)

    monkeypatch.setenv("GOOGLE_CREDENTIALS_PATH", "/secrets/credentials.json")
    monkeypatch.setenv("GOOGLE_TOKEN_PATH", "/secrets/token.json")
    monkeypatch.setenv("GOOGLE_INSERT", "true")
    monkeypatch.setenv("GOOGLE_CALENDAR_NAME", "Company Earnings")
    monkeypatch.setenv("GOOGLE_CREATE_CALENDAR", "1")
    monkeypatch.setenv("MARKET_EVENTS", "true")
    monkeypatch.setenv("MACRO_EVENTS", "1")
    monkeypatch.setenv("SOURCE_TIMEZONE", "America/New_York")
    monkeypatch.setenv("TARGET_TIMEZONE", "Asia/Shanghai")
    monkeypatch.setenv("EVENT_DURATION_MINUTES", "75")
    monkeypatch.setenv("SESSION_TIMES", "BMO=07:45,AMC=19:00")
    monkeypatch.setenv("MACRO_EVENT_KEYWORDS", "FOMC,NFP")
    monkeypatch.setenv("MACRO_EVENT_SOURCE", "benzinga")
    monkeypatch.setenv("INCREMENTAL_SYNC", "true")
    monkeypatch.setenv("SYNC_STATE_PATH", "state/cache.json")
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
        google_calendar_id=None,
        google_calendar_name=None,
        google_create_calendar=False,
        source_tz=None,
        target_tz=None,
        event_duration=None,
        session_times=None,
        market_events=None,
        icloud_insert=False,
        icloud_id=None,
        icloud_app_pass=None,
        macro_events=False,
        macro_event_keywords=None,
        macro_event_source=None,
        incremental=False,
        sync_state_path=None,
    )

    config_base = Path(tmp_path) / "config_dir"
    config_base.mkdir()

    options = build_runtime_options(
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
    assert options.google_calendar_name == "Company Earnings"
    assert options.google_create_calendar is True
    assert options.source_timezone == "America/New_York"
    assert options.target_timezone == "Asia/Shanghai"
    assert options.event_duration_minutes == 75
    assert options.session_time_map == {"BMO": "07:45", "AMC": "19:00"}
    assert options.market_events is True
    assert options.icloud_insert is True
    assert options.icloud_id == "user@icloud.com"
    assert options.icloud_app_pass == "pass-1234"
    assert options.macro_events is True
    assert options.macro_event_keywords == ["FOMC", "NFP"]
    assert options.macro_event_source == "benzinga"
    assert options.incremental_sync is True
    assert options.sync_state_path.endswith("state/cache.json")


def test_build_runtime_options_resolves_paths_relative_to_config(tmp_path, monkeypatch):
    _clear_env(monkeypatch)

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
        google_calendar_id=None,
        google_calendar_name=None,
        google_create_calendar=False,
        source_tz=None,
        target_tz=None,
        event_duration=None,
        session_times=None,
        market_events=False,
        icloud_insert=False,
        icloud_id=None,
        icloud_app_pass=None,
        macro_events=False,
        macro_event_keywords=None,
        macro_event_source=None,
        incremental=False,
        sync_state_path=None,
    )

    options = build_runtime_options(
        parsed,
        config,
        config_base=config_base,
        project_root=tmp_path,
    )

    assert options.google_credentials == str(config_base / "secrets/credentials.json")
    assert options.google_token == str(config_base / "secrets/token.json")
    assert options.google_calendar_id == "primary"
    assert options.source_timezone == DEFAULT_SOURCE_TIMEZONE
    assert options.target_timezone == DEFAULT_TARGET_TIMEZONE
    assert options.event_duration_minutes == DEFAULT_EVENT_DURATION_MINUTES
    assert options.session_time_map == DEFAULT_SESSION_TIMES
    assert options.market_events is False
    assert options.macro_events is False
    assert options.macro_event_source == "benzinga"
    assert options.incremental_sync is False
    assert options.sync_state_path is None


def test_build_runtime_options_rejects_non_benzinga(tmp_path, monkeypatch):
    _clear_env(monkeypatch)
    config = {"symbols": ["AAPL"], "macro_event_source": "fmp"}
    parsed = SimpleNamespace(
        symbols=None,
        source=None,
        days=None,
        export_ics=None,
        google_insert=False,
        google_credentials=None,
        google_token=None,
        google_calendar_id=None,
        google_calendar_name=None,
        google_create_calendar=False,
        source_tz=None,
        target_tz=None,
        event_duration=None,
        session_times=None,
        market_events=False,
        icloud_insert=False,
        icloud_id=None,
        icloud_app_pass=None,
        macro_events=False,
        macro_event_keywords=None,
        macro_event_source=None,
        incremental=False,
        sync_state_path=None,
    )

    with pytest.raises(ValueError):
        build_runtime_options(
            parsed,
            config,
            config_base=None,
            project_root=Path(tmp_path),
        )
