from datetime import date

import pytest

from toolkits.calendar_svc import fetch_macro_events
from toolkits.calendar_svc import RuntimeOptions


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
        macro_event_source="benzinga",
        incremental_sync=False,
        sync_state_path=None,
    )
    params.update(overrides)
    return RuntimeOptions(**params)


def test_fetch_macro_events_includes_high_importance_events(monkeypatch):
    monkeypatch.setenv("BENZINGA_API_KEY", "bz_token")

    captured = {}
    payload = {
        "economics": [
            {
                "event_name": "FOMC Interest Rate Decision",
                "event_date": "2024-09-18",
                "event_time": "14:00",
                "country": "USA",
                "importance": 4,
                "actual": "5.50%",
                "consensus": "5.50%",
                "event_category": "FOMC",
            },
            {
                "event_name": "Housing Starts",
                "event_date": "2024-09-18",
                "event_time": "08:30",
                "country": "USA",
                "importance": 3,
                "event_category": "Housing",
            },
            {
                "event_name": "Housing Starts",
                "event_date": "2024-09-18",
                "event_time": "08:30",
                "country": "USA",
                "importance": 3,
                "event_category": "Housing",
            },
        ]
    }

    def fake_get(params):  # noqa: ANN001
        captured["params"] = params
        return _Response(payload)

    monkeypatch.setattr("toolkits.calendar_svc.macro_events._http_get", fake_get)

    options = _base_options()
    events = fetch_macro_events(date(2024, 9, 1), date(2024, 9, 30), options)

    assert captured["params"]["parameters[date_from]"] == "2024-09-01"
    assert captured["params"]["country"] == "USA"
    assert len(events) == 3
    symbols = {evt.symbol: evt for evt in events}
    fomc = symbols["MACRO-FOMC-INTEREST-RATE-DECISION"]
    assert fomc.source == "Benzinga-Economic"
    assert fomc.session == "FOMC"
    assert "Importance: 4" in fomc.notes
    housing = next(evt for evt in events if evt.symbol.startswith("MACRO-HOUSING-STARTS"))
    assert housing.session == "HOUSING"


def test_fetch_macro_events_requires_api_key(monkeypatch):
    monkeypatch.delenv("BENZINGA_API_KEY", raising=False)
    options = _base_options()
    with pytest.raises(RuntimeError):
        fetch_macro_events(date(2024, 1, 1), date(2024, 1, 31), options)


def test_fetch_macro_events_handles_results_key(monkeypatch):
    monkeypatch.setenv("BENZINGA_API_KEY", "bz_token")

    payload = {
        "results": [
            {
                "event_name": "30-Year Bond Auction",
                "event_date": "2024-08-08",
                "event_time": "13:00",
                "country": "USA",
                "importance": 3,
                "event_category": "Treasury",
            },
            {
                "event_name": "Conference Board Index",
                "event_date": "2024-08-08",
                "event_time": "10:00",
                "country": "USA",
                "importance": 3,
                "event_category": "Economic",
            },
        ]
    }

    monkeypatch.setattr(
        "toolkits.calendar_svc.macro_events._http_get",
        lambda params: _Response(payload),
    )

    options = _base_options()
    events = fetch_macro_events(date(2024, 8, 1), date(2024, 8, 31), options)

    assert len(events) == 2
    sessions = {event.session for event in events}
    assert "TREASURY" in sessions
    assert "ECONOMIC" in sessions
