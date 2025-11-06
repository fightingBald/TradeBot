"""Market calendar helpers (四巫日 / OPEX / VIX 结算)."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Iterable, List
from zoneinfo import ZoneInfo

from .domain import EarningsEvent
from .settings import RuntimeOptions


def _nth_weekday(year: int, month: int, weekday: int) -> date | None:
    first = date(year, month, 1)
    offset = (weekday - first.weekday()) % 7
    candidate = first + timedelta(days=offset + 14)
    if candidate.month == month:
        return candidate
    return None


def _month_range(start: date, end: date) -> Iterable[tuple[int, int]]:
    year, month = start.year, start.month
    while date(year, month, 1) <= date(end.year, end.month, 1):
        yield year, month
        if month == 12:
            year += 1
            month = 1
        else:
            month += 1


def generate_market_events(
    start: date, end: date, options: RuntimeOptions
) -> List[EarningsEvent]:
    """生成四巫日 / OPEX / VIX 结算等市场事件。"""
    tz = ZoneInfo(options.source_timezone)
    duration = timedelta(minutes=options.event_duration_minutes)
    default_time = time(9, 30)
    events: List[EarningsEvent] = []

    def add_event(event_date: date, symbol: str, title: str, notes: str) -> None:
        if event_date < start or event_date > end:
            return
        start_at = datetime.combine(event_date, default_time, tzinfo=tz)
        end_at = start_at + duration
        events.append(
            EarningsEvent(
                symbol=symbol,
                date=event_date,
                session=title.upper(),
                source="MarketCalendar",
                notes=notes,
                start_at=start_at,
                end_at=end_at,
                timezone=tz.key,
            )
        )

    for year, month in _month_range(start, end):
        third_friday = _nth_weekday(year, month, 4)
        if third_friday:
            add_event(
                third_friday,
                symbol="MARKET-OPEX",
                title="OPEX",
                notes="Monthly options expiration (third Friday)",
            )
            if month in {3, 6, 9, 12}:
                add_event(
                    third_friday,
                    symbol="MARKET-FOUR-WITCHES",
                    title="Four Witches",
                    notes="Quadruple Witching (stocks & futures options)",
                )
        third_wed = _nth_weekday(year, month, 2)
        if third_wed:
            add_event(
                third_wed,
                symbol="MARKET-VIX-OPTIONS",
                title="VIX Options",
                notes="VIX options settlement (third Wednesday)",
            )
            futures_day = third_wed + timedelta(days=1)
            add_event(
                futures_day,
                symbol="MARKET-VIX-FUTURES",
                title="VIX Futures",
                notes="VIX futures settlement (following options)",
            )
    return events


__all__ = ["generate_market_events"]
