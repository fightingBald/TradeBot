from datetime import date, datetime

from zoneinfo import ZoneInfo

from data_sources.earnings_to_calendar.domain import EarningsEvent
from data_sources.earnings_to_calendar.runner import run
import data_sources.earnings_to_calendar.runner as runner_mod
from data_sources.earnings_to_calendar.settings import RuntimeOptions
from data_sources.earnings_to_calendar import providers as providers_mod
import data_sources.earnings_to_calendar.calendars as calendars_mod


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
