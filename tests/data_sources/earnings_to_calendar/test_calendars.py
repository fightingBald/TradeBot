from datetime import date, datetime
from zoneinfo import ZoneInfo

import src.earnings.calendar.calendars as calendars_mod
from src.earnings.calendar.calendars import build_ics
from src.earnings.calendar.domain import EarningsEvent

from .conftest import StubGoogleService


def test_build_ics_generates_expected_fields():
    ny = ZoneInfo("America/New_York")
    berlin = ZoneInfo("Europe/Berlin")
    event = EarningsEvent(
        symbol="AAPL",
        date=date(2024, 1, 25),
        session="AMC",
        source="FMP",
        url="https://example.com",
        start_at=datetime(2024, 1, 25, 17, 0, tzinfo=ny),
        end_at=datetime(2024, 1, 25, 18, 0, tzinfo=ny),
    )
    ics = build_ics(
        [event],
        prodid="-//test//",
        target_timezone=berlin.key,
        default_duration_minutes=90,
    )

    assert "PRODID:-//test//" in ics
    assert "SUMMARY:AAPL Earnings (AMC)" in ics
    assert "DESCRIPTION:Earnings date from FMP." in ics
    assert "URL:https://example.com" in ics
    assert "DTSTART;TZID=Europe/Berlin:20240125T230000" in ics
    assert "DTEND;TZID=Europe/Berlin:20240126T000000" in ics


def test_google_insert_creates_calendar_when_missing(monkeypatch):
    service = StubGoogleService()
    monkeypatch.setattr(
        calendars_mod, "_get_google_service", lambda *args, **kwargs: service
    )

    ny = ZoneInfo("America/New_York")
    event = EarningsEvent(
        symbol="AAPL",
        date=date(2024, 5, 1),
        session="AMC",
        source="FMP",
        start_at=datetime(2024, 5, 1, 17, 0, tzinfo=ny),
        end_at=datetime(2024, 5, 1, 18, 0, tzinfo=ny),
        timezone="America/New_York",
    )

    calendar_id = calendars_mod.google_insert(
        [event],
        calendar_id=None,
        creds_path="cred.json",
        token_path="token.json",
        calendar_name="Company Earnings",
        create_if_missing=True,
        target_timezone="Europe/Berlin",
        default_duration_minutes=75,
    )

    assert calendar_id in service.calendars_data
    assert service.calendars_data[calendar_id] == "Company Earnings"
    assert len(service.calendar_inserts) == 1
    assert len(service.events_data[calendar_id]) == 1
    stored_event = service.events_data[calendar_id][0]
    assert "dateTime" in stored_event["start"]
    assert stored_event["start"]["timeZone"] == "Europe/Berlin"


def test_google_insert_upserts_existing(monkeypatch):
    service = StubGoogleService({"primary": "Primary"})
    monkeypatch.setattr(
        calendars_mod, "_get_google_service", lambda *args, **kwargs: service
    )

    ny = ZoneInfo("America/New_York")
    base_event = EarningsEvent(
        symbol="MSFT",
        date=date(2024, 6, 10),
        session="BMO",
        source="FMP",
        start_at=datetime(2024, 6, 10, 8, 0, tzinfo=ny),
        end_at=datetime(2024, 6, 10, 9, 0, tzinfo=ny),
        timezone="America/New_York",
    )

    calendars_mod.google_insert(
        [base_event],
        calendar_id="primary",
        creds_path="cred.json",
        token_path="token.json",
        target_timezone="America/Chicago",
        default_duration_minutes=45,
    )

    assert len(service.events_data["primary"]) == 1
    first_event = service.events_data["primary"][0]
    event_id = first_event["id"]

    updated_event = EarningsEvent(
        symbol="MSFT",
        date=date(2024, 6, 10),
        session="BMO",
        source="FMP",
        notes="Updated desc",
        start_at=datetime(2024, 6, 10, 8, 0, tzinfo=ny),
        end_at=datetime(2024, 6, 10, 9, 0, tzinfo=ny),
        timezone="America/New_York",
    )

    calendars_mod.google_insert(
        [updated_event],
        calendar_id="primary",
        creds_path="cred.json",
        token_path="token.json",
        target_timezone="America/Chicago",
        default_duration_minutes=45,
    )

    assert len(service.events_data["primary"]) == 1
    stored_event = service.events_data["primary"][0]
    assert stored_event["id"] == event_id
    assert "Updated desc" in stored_event["description"]
    assert stored_event["start"]["timeZone"] == "America/Chicago"
    assert len(service.insert_calls) == 1
    assert len(service.update_calls) == 1
