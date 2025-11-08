from __future__ import annotations

import os
from datetime import date

import pytest
import requests

from lib.calendar_svc import _slugify, fetch_macro_events
from lib.calendar_svc import RuntimeOptions

BASE_URL = "https://api.benzinga.com/api/v2.1/calendar/economics"
TOKEN = "bz.PS2LUOAUAKAL3IXC5FDUFXYRQX4DXVNS"
PARAMS = {
    "parameters[date_from]": "2025-11-08",
    "parameters[date_to]": "2028-05-07",
    "parameters[importance]": 3,
    "country": "USA",
}
HEADERS = {"accept": "application/json"}

RUN_LIVE = os.getenv("RUN_BENZINGA_LIVE_TEST") == "1"

if RUN_LIVE:
    os.environ.setdefault("BENZINGA_API_KEY", TOKEN)

pytestmark = pytest.mark.skipif(
    not RUN_LIVE, reason="Set RUN_BENZINGA_LIVE_TEST=1 to run live Benzinga test"
)


def _direct_fetch() -> list[dict]:
    response = requests.get(
        BASE_URL,
        params={"token": TOKEN, **PARAMS, "page": 0, "pagesize": 200},
        headers=HEADERS,
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()
    economics = payload.get("economics") or payload.get("results") or []
    return [item for item in economics if isinstance(item, dict)]


def _build_options() -> RuntimeOptions:
    return RuntimeOptions(
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


def test_benzinga_direct_matches_module() -> None:
    try:
        raw_items = _direct_fetch()
    except requests.RequestException as exc:  # pragma: no cover - live only
        pytest.skip(f"Benzinga API unreachable: {exc}")

    options = _build_options()
    start = date.fromisoformat(PARAMS["parameters[date_from]"])
    end = date.fromisoformat(PARAMS["parameters[date_to]"])

    try:
        module_events = fetch_macro_events(start, end, options)
    except requests.RequestException as exc:  # pragma: no cover - live only
        pytest.skip(f"Benzinga API unreachable via module: {exc}")

    direct_set = {
        (_slugify(str(item["event_name"])), item["date"][:10])
        for item in raw_items
        if item.get("event_name") and item.get("date")
    }
    module_set = {
        (event.symbol.replace("MACRO-", ""), event.iso_date) for event in module_events
    }

    print(module_set)
    assert module_set == direct_set
