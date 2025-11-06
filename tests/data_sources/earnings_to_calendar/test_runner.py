from datetime import date, datetime
from zoneinfo import ZoneInfo

import data_sources.earnings_to_calendar.calendars as calendars_mod
import data_sources.earnings_to_calendar.runner as runner_mod
from data_sources.earnings_to_calendar import providers as providers_mod
from data_sources.earnings_to_calendar.domain import EarningsEvent
from data_sources.earnings_to_calendar.runner import run
from data_sources.earnings_to_calendar.settings import RuntimeOptions


class _StubProvider:
    def __init__(self, api_key, **kwargs):
        self.api_key = api_key
        self.kwargs = kwargs

    def fetch(self, symbols, since, until):
        tz = ZoneInfo("America/New_York")
        base = EarningsEvent(
            symbol="AAPL",
            date=date(2024, 3, 20),
            session="AMC",
            source="Stub",
            start_at=datetime(2024, 3, 20, 17, 0, tzinfo=tz),
            end_at=datetime(2024, 3, 20, 18, 0, tzinfo=tz),
            timezone="America/New_York",
        )
        duplicate = base.model_copy()
        duplicate.source = "Dup"
        return [base, duplicate]


def test_run_pipeline_writes_outputs(tmp_path, monkeypatch):
    monkeypatch.setenv("FMP_API_KEY", "token")
    monkeypatch.setitem(providers_mod.PROVIDERS, "fmp", _StubProvider)

    google_calls = {}

    def fake_google_insert(events, **kwargs):
        google_calls["events"] = list(events)
        google_calls["kwargs"] = kwargs
        return "calendar-123"

    monkeypatch.setattr(calendars_mod, "google_insert", fake_google_insert)
    monkeypatch.setattr(runner_mod, "google_insert", fake_google_insert)

    ics_path = tmp_path / "earnings.ics"

    options = RuntimeOptions(
        symbols=["AAPL"],
        source="fmp",
        days=30,
        export_ics=str(ics_path),
        google_insert=True,
        google_credentials="cred.json",
        google_token="token.json",
        google_calendar_id=None,
        google_calendar_name="Company Earnings",
        google_create_calendar=True,
        source_timezone="America/New_York",
        target_timezone="Europe/Berlin",
        event_duration_minutes=60,
        session_time_map={"AMC": "17:00"},
        market_events=False,
        icloud_insert=False,
        icloud_id=None,
        icloud_app_pass=None,
        macro_events=False,
        macro_event_keywords=[],
        incremental_sync=False,
        sync_state_path=None,
    )

    summary = run(options, today=date(2024, 3, 1))

    assert summary.since == date(2024, 3, 1)
    assert summary.google_calendar_id == "calendar-123"
    assert summary.ics_path == str(ics_path)
    assert ics_path.exists()
    # Events should be deduplicated before write
    assert len(summary.events) == 1
    assert google_calls["kwargs"]["calendar_name"] == "Company Earnings"
    assert len(google_calls["events"]) == 1


def test_run_incremental_skips_when_state_matches(tmp_path, monkeypatch):
    monkeypatch.setenv("FMP_API_KEY", "token")
    monkeypatch.setitem(providers_mod.PROVIDERS, "fmp", _StubProvider)

    google_batches: list[list] = []

    def fake_google_insert(events, **kwargs):
        google_batches.append(list(events))
        return "calendar-xyz"

    monkeypatch.setattr(calendars_mod, "google_insert", fake_google_insert)
    monkeypatch.setattr(runner_mod, "google_insert", fake_google_insert)

    sync_path = tmp_path / "sync-state.json"

    base_options = dict(
        symbols=["AAPL"],
        source="fmp",
        days=30,
        export_ics=None,
        google_insert=True,
        google_credentials="cred.json",
        google_token="token.json",
        google_calendar_id=None,
        google_calendar_name="Company Earnings",
        google_create_calendar=True,
        source_timezone="America/New_York",
        target_timezone="America/New_York",
        event_duration_minutes=60,
        session_time_map={"AMC": "17:00"},
        market_events=False,
        icloud_insert=False,
        icloud_id=None,
        icloud_app_pass=None,
        macro_events=False,
        macro_event_keywords=[],
        incremental_sync=True,
        sync_state_path=str(sync_path),
    )

    options = RuntimeOptions(**base_options)

    first_summary = run(options, today=date(2024, 3, 1))
    assert google_batches and len(google_batches[0]) == 1
    assert first_summary.sync_stats == {
        "created": 1,
        "updated": 0,
        "skipped": 0,
        "total": 1,
    }

    google_batches.clear()

    second_summary = run(options, today=date(2024, 3, 1))
    assert not google_batches  # 没有再次调用写入
    assert second_summary.sync_stats == {
        "created": 0,
        "updated": 0,
        "skipped": 1,
        "total": 1,
    }
    assert sync_path.exists()
