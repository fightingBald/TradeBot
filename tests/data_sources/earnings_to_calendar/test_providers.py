from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from lib.calendar_svc import (
    DEFAULT_EVENT_DURATION_MINUTES, DEFAULT_SESSION_TIMES,
    DEFAULT_SOURCE_TIMEZONE)
from lib.calendar_svc.providers import (FinnhubEarningsProvider,
                                    FmpEarningsProvider)

from .conftest import StubResponse


def test_fmp_provider_filters_and_normalizes(monkeypatch):
    payload = [
        {"symbol": "aapl", "date": "2024-01-25", "time": "AMC"},
        {"symbol": "msft", "earningsDate": "2024-01-30"},
        {"symbol": "tsla", "date": "bad-date"},
    ]

    captured: dict[str, object] = {}

    def fake_httpx_get(url, *, headers, timeout):  # noqa: ANN001
        captured["url"] = url
        captured["headers"] = headers
        captured["timeout"] = timeout
        return StubResponse(payload)

    monkeypatch.setattr("lib.calendar_svc.providers.httpx.get", fake_httpx_get)

    provider = FmpEarningsProvider(
        "token",
        source_timezone=DEFAULT_SOURCE_TIMEZONE,
        session_times=DEFAULT_SESSION_TIMES,
        event_duration_minutes=DEFAULT_EVENT_DURATION_MINUTES,
    )
    events = provider.fetch(["AAPL", "MSFT"], date(2024, 1, 1), date(2024, 1, 31))

    assert captured["headers"]["User-Agent"] == "earnings-to-calendar/1.0"
    assert "from=2024-01-01" in captured["url"]
    assert "to=2024-01-31" in captured["url"]
    assert len(events) == 2
    ny = ZoneInfo("America/New_York")
    assert events[0].start_at == datetime(2024, 1, 25, 17, 0, tzinfo=ny)
    assert events[0].end_at == events[0].start_at + timedelta(
        minutes=DEFAULT_EVENT_DURATION_MINUTES
    )
    assert events[0].timezone == "America/New_York"
    assert events[1].start_at is None
    assert events[1].end_at is None
    assert events[1].timezone == "America/New_York"


def test_finnhub_provider_handles_nested_payload(monkeypatch):
    payload = {
        "earningsCalendar": [
            {"symbol": "AAPL", "date": "2024-01-25", "hour": "bmo"},
            {"symbol": "GOOGL", "date": None},
        ]
    }

    monkeypatch.setattr(
        "lib.calendar_svc.providers.httpx.get",
        lambda url, *, headers, timeout: StubResponse(payload),
    )

    provider = FinnhubEarningsProvider(
        "token",
        source_timezone=DEFAULT_SOURCE_TIMEZONE,
        session_times=DEFAULT_SESSION_TIMES,
        event_duration_minutes=DEFAULT_EVENT_DURATION_MINUTES,
    )
    events = provider.fetch(["AAPL", "GOOGL"], date(2024, 1, 1), date(2024, 1, 31))

    assert len(events) == 1
    ny = ZoneInfo("America/New_York")
    assert events[0].start_at == datetime(2024, 1, 25, 8, 0, tzinfo=ny)
    assert events[0].end_at == events[0].start_at + timedelta(
        minutes=DEFAULT_EVENT_DURATION_MINUTES
    )
