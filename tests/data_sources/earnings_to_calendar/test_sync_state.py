from datetime import date, datetime
from zoneinfo import ZoneInfo

from toolkits.calendar_svc.domain import EarningsEvent
from toolkits.calendar_svc import (
    build_sync_state,
    diff_events,
    load_sync_state,
    save_sync_state,
)


def _sample_event(symbol: str = "AAPL", *, notes: str | None = None) -> EarningsEvent:
    tz = ZoneInfo("America/New_York")
    return EarningsEvent(
        symbol=symbol,
        date=date(2024, 6, 10),
        session="AMC",
        source="FMP",
        notes=notes,
        start_at=datetime(2024, 6, 10, 17, 0, tzinfo=tz),
        end_at=datetime(2024, 6, 10, 18, 0, tzinfo=tz),
        timezone=tz.key,
    )


def test_diff_events_detects_create_update(tmp_path):
    event = _sample_event()
    empty_state = load_sync_state(None)

    diff = diff_events([event], empty_state)
    assert len(diff.to_create) == 1
    assert not diff.to_update
    assert not diff.unchanged

    state = build_sync_state(
        [event], diff.fingerprints, since=date(2024, 6, 1), until=date(2024, 7, 1)
    )
    state_path = tmp_path / "state.json"
    save_sync_state(str(state_path), state)

    loaded_state = load_sync_state(str(state_path))
    unchanged_diff = diff_events([event], loaded_state)
    assert len(unchanged_diff.unchanged) == 1
    assert not unchanged_diff.to_create
    assert not unchanged_diff.to_update

    updated_event = _sample_event(notes="updated")
    update_diff = diff_events([updated_event], loaded_state)
    assert len(update_diff.to_update) == 1
    assert not update_diff.to_create


def test_build_sync_state_overwrites_previous_entries(tmp_path):
    e1 = _sample_event("AAPL")
    e2 = _sample_event("MSFT")
    diff = diff_events([e1, e2], load_sync_state(None))
    state = build_sync_state(
        [e1, e2], diff.fingerprints, since=date(2024, 1, 1), until=date(2024, 2, 1)
    )

    path = tmp_path / "sync.json"
    save_sync_state(str(path), state)

    loaded = load_sync_state(str(path))
    assert len(loaded.events) == 2
    assert loaded.time_window == {"since": "2024-01-01", "until": "2024-02-01"}
