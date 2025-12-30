"""Minimal Benzinga economic calendar integration."""

from __future__ import annotations

import os
import re
from collections.abc import Mapping
from datetime import date, datetime, time as dt_time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import requests

from .defaults import DEFAULT_EVENT_DURATION_MINUTES, DEFAULT_TIMEOUT_SECONDS, USER_AGENT
from .domain import EarningsEvent
from .logging_utils import get_logger
from .settings import RuntimeOptions

logger = get_logger()

BENZINGA_ECONOMIC_URL = "https://api.benzinga.com/api/v2.1/calendar/economics"


def _require_api_key(env_var: str, provider_name: str) -> str:
    api_key = os.getenv(env_var)
    if not api_key:
        logger.error("缺少 %s，无法使用 %s 数据源", env_var, provider_name)
        raise RuntimeError(f"缺少 {env_var}")
    return api_key


def _extract_items(payload: Any) -> list[Mapping[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, Mapping)]
    if isinstance(payload, Mapping):
        for key in ("economics", "results", "data", "items"):
            maybe = payload.get(key)
            if isinstance(maybe, list):
                return [item for item in maybe if isinstance(item, Mapping)]
    return []


def _slugify(text: str) -> str:
    slug = re.sub(r"[^A-Z0-9]+", "-", text.upper()).strip("-")
    return slug or "MACRO"


def _parse_time_value(value: Any) -> dt_time | None:
    if value in (None, "", "N/A"):
        return None
    text = str(value).strip()
    formats = ["%H:%M:%S", "%H:%M", "%I:%M %p"]
    for fmt in formats:
        try:
            return datetime.strptime(text, fmt).time()  # noqa: DTZ007
        except ValueError:
            continue
    return None


def _parse_event_datetime(item: Mapping[str, Any], tz: ZoneInfo) -> tuple[date | None, datetime | None]:
    raw_date = item.get("date") or item.get("event_date")
    if not raw_date:
        return None, None
    try:
        event_date = date.fromisoformat(str(raw_date)[:10])
    except ValueError:
        return None, None
    raw_time = item.get("time") or item.get("event_time")
    time_obj = _parse_time_value(raw_time)
    if time_obj is None:
        return event_date, None
    start = datetime.combine(event_date, time_obj, tzinfo=tz)
    return event_date, start


def _build_notes(item: Mapping[str, Any]) -> str:
    fields = []
    for key in ("description", "notes"):
        text = item.get(key)
        if text:
            fields.append(str(text).strip())
    for key, label in (("actual", "Actual"), ("consensus", "Consensus"), ("previous", "Previous")):
        value = item.get(key)
        if value not in (None, ""):
            fields.append(f"{label}: {value}")
    importance = item.get("importance")
    if importance not in (None, ""):
        fields.append(f"Importance: {importance}")
    return "; ".join(fields) if fields else "Macro event from Benzinga"


def _http_get(params: Mapping[str, Any]) -> requests.Response:
    return requests.get(
        BENZINGA_ECONOMIC_URL,
        params=params,
        headers={"Accept": "application/json", "User-Agent": USER_AGENT},
        timeout=DEFAULT_TIMEOUT_SECONDS,
    )


def fetch_macro_events(start: date, end: date, options: RuntimeOptions) -> list[EarningsEvent]:
    api_key = _require_api_key("BENZINGA_API_KEY", "Benzinga")

    params = {
        "token": api_key,
        "parameters[date_from]": start.isoformat(),
        "parameters[date_to]": end.isoformat(),
        "parameters[importance]": 3,
        "country": "USA",
        "page": 0,
        "pagesize": 200,
    }

    response = _http_get(params)
    response.raise_for_status()
    items = _extract_items(response.json())

    tz = ZoneInfo(options.source_timezone)
    duration = timedelta(minutes=options.event_duration_minutes or DEFAULT_EVENT_DURATION_MINUTES)
    events: list[EarningsEvent] = []

    for item in items:
        event_name = str(item.get("event_name") or item.get("event") or "").strip()
        if not event_name:
            continue
        event_date, start_at = _parse_event_datetime(item, tz)
        if event_date is None:
            continue
        end_at = start_at + duration if start_at else None
        session = str(item.get("event_category") or "MACRO").upper()
        symbol = f"MACRO-{_slugify(event_name)}"
        notes = _build_notes(item)
        logger.info(f'Benzinga 返回事件 "{event_name}" - {event_date}')
        events.append(
            EarningsEvent(
                symbol=symbol,
                date=event_date,
                session=session,
                source="Benzinga-Economic",
                notes=notes,
                start_at=start_at,
                end_at=end_at,
                timezone=tz.key,
            )
        )

    logger.info("Benzinga 返回 %d 条事件", len(events))

    return events


__all__ = ["fetch_macro_events"]
