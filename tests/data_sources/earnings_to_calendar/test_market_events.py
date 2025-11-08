from datetime import date, datetime
from zoneinfo import ZoneInfo

from toolkits.calendar_svc import generate_market_events
from toolkits.calendar_svc import RuntimeOptions


def test_generate_market_events():
    options = RuntimeOptions(
        symbols=[],
        source="fmp",
        days=0,
        export_ics=None,
        google_insert=False,
        google_credentials="",
        google_token="",
        google_calendar_id=None,
        google_calendar_name=None,
        google_create_calendar=False,
        source_timezone="America/New_York",
        target_timezone="Europe/Berlin",
        event_duration_minutes=60,
        session_time_map={"BMO": "08:00", "AMC": "17:00"},
        market_events=True,
        icloud_insert=False,
        icloud_id=None,
        icloud_app_pass=None,
        macro_events=False,
        macro_event_keywords=[],
        incremental_sync=False,
        sync_state_path=None,
    )

    events = generate_market_events(date(2024, 3, 1), date(2024, 3, 31), options)
    assert len(events) == 4
    kinds = {e.symbol: e for e in events}
    assert set(kinds) == {
        "MARKET-OPEX",
        "MARKET-FOUR-WITCHES",
        "MARKET-VIX-OPTIONS",
        "MARKET-VIX-FUTURES",
    }
    ny = ZoneInfo("America/New_York")
    assert kinds["MARKET-OPEX"].start_at == datetime(2024, 3, 15, 9, 30, tzinfo=ny)
    assert kinds["MARKET-VIX-OPTIONS"].start_at.date() == date(2024, 3, 20)
    assert kinds["MARKET-VIX-FUTURES"].start_at.date() == date(2024, 3, 21)
    assert all(ev.timezone == "America/New_York" for ev in events)
