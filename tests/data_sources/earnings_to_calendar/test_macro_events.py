from datetime import date

import pytest

from data_sources.earnings_to_calendar.macro_events import fetch_macro_events
from data_sources.earnings_to_calendar.settings import RuntimeOptions


class _Response:
    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload

    def raise_for_status(self):
        return None


def _base_options(**overrides):
    params = dict(
        symbols=["AAPL"],
        source="fmp",
        days=30,
        export_ics=None,
        google_insert=False,
        google_credentials="cred.json",
        google_token="token.json",
        google_calendar_id=None,
        google_calendar_name=None,
        google_create_calendar=False,
        source_timezone="America/New_York",
        target_timezone="America/New_York",
        event_duration_minutes=60,
        session_time_map={"AMC": "17:00"},
        market_events=False,
        icloud_insert=False,
        icloud_id=None,
        icloud_app_pass=None,
        macro_events=True,
        macro_event_keywords=[],
        incremental_sync=False,
        sync_state_path=None,
    )
    params.update(overrides)
    return RuntimeOptions(**params)


def test_fetch_macro_events_filters_known_events(monkeypatch):
    monkeypatch.setenv("FMP_API_KEY", "demo")

    captured = {}

    payload = [
        {
            "event": "FOMC Meeting",
            "date": "2024-09-18 14:00:00",
            "country": "United States",
            "actual": "5.50%",
            "forecast": "5.50%",
            "previous": "5.50%",
            "importance": "High",
        },
        {
            "event": "Housing Starts",
            "date": "2024-09-18 08:30:00",
            "country": "United States",
        },
    ]

    def fake_get(url, params=None, headers=None, timeout=None):  # noqa: ANN001
        captured["url"] = url
        captured["params"] = params
        captured["headers"] = headers
        captured["timeout"] = timeout
        return _Response(payload)

    monkeypatch.setattr("data_sources.earnings_to_calendar.macro_events.requests.get", fake_get)

    options = _base_options()
    events = fetch_macro_events(date(2024, 9, 1), date(2024, 9, 30), options)

    assert captured["url"].endswith("economic-calendar")
    assert captured["params"]["from"] == "2024-09-01"
    assert captured["params"]["to"] == "2024-09-30"
    assert len(events) == 1
    event = events[0]
    assert event.symbol == "MACRO-FOMC-MEETING"
    assert event.session == "FOMC"
    assert event.notes.startswith("Country: United States")


def test_fetch_macro_events_supports_custom_keywords(monkeypatch):
    monkeypatch.setenv("FMP_API_KEY", "demo")

    payload = [
        {
            "event": "30-Year Bond Auction",
            "date": "2024-08-08 13:00:00",
            "country": "United States",
        }
    ]

    monkeypatch.setattr(
        "data_sources.earnings_to_calendar.macro_events.requests.get",
        lambda *args, **kwargs: _Response(payload),
    )

    options = _base_options(macro_event_keywords=["Treasury"])
    events = fetch_macro_events(date(2024, 8, 1), date(2024, 8, 31), options)

    assert len(events) == 1
    assert events[0].session == "TREASURY"


def test_fetch_macro_events_requires_api_key(monkeypatch):
    monkeypatch.delenv("FMP_API_KEY", raising=False)
    options = _base_options()
    with pytest.raises(RuntimeError):
        fetch_macro_events(date(2024, 1, 1), date(2024, 1, 31), options)
