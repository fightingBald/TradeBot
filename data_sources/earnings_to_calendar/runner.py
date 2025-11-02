"""High-level orchestration helpers for earnings-to-calendar."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import List, Sequence

from zoneinfo import ZoneInfo

from .calendars import build_ics, google_insert, icloud_caldav_insert
from .domain import EarningsEvent, deduplicate_events
from .logging_utils import get_logger
from .market_events import generate_market_events
from .providers import PROVIDERS, EarningsDataProvider
from .settings import RuntimeOptions

logger = get_logger()


@dataclass
class RunSummary:
    since: date
    until: date
    events: List[EarningsEvent]
    google_calendar_id: str | None = None
    ics_path: str | None = None
    icloud_calendar_name: str | None = None


def _resolve_provider(options: RuntimeOptions) -> EarningsDataProvider:
    if options.source not in PROVIDERS:
        raise ValueError(f"Unsupported data source: {options.source}")
    env_var = "FMP_API_KEY" if options.source == "fmp" else "FINNHUB_API_KEY"
    api_key = os.getenv(env_var)
    if not api_key:
        logger.error("环境变量 %s 未配置，无法使用数据源 %s", env_var, options.source)
        raise RuntimeError(f"缺少 {env_var}")

    provider_cls = PROVIDERS[options.source]
    return provider_cls(
        api_key,
        source_timezone=options.source_timezone,
        session_times=options.session_time_map,
        event_duration_minutes=options.event_duration_minutes,
    )


def collect_events(
    options: RuntimeOptions,
    *,
    since: date,
    until: date,
) -> List[EarningsEvent]:
    provider = _resolve_provider(options)
    logger.info(
        "开始拉取数据：source=%s symbols=%s 窗口=%s~%s",
        options.source,
        ",".join(options.symbols),
        since,
        until,
    )
    events = provider.fetch(options.symbols, since, until)
    if options.market_events:
        extras = generate_market_events(since, until, options)
        if extras:
            logger.info("追加市场事件 %d 条", len(extras))
            events.extend(extras)
    unique_events = deduplicate_events(events)
    logger.info("共获取事件 %d 条（去重后 %d 条）", len(events), len(unique_events))
    return unique_events


def _format_google_event_lines(events: Sequence[EarningsEvent], options: RuntimeOptions) -> str:
    fallback_tz = ZoneInfo(options.target_timezone)

    def _event_sort_key(item: EarningsEvent) -> tuple[date, datetime, str]:
        start = item.start_at
        if start is None:
            start = datetime.combine(item.date, time.min, tzinfo=fallback_tz)
        return (item.date, start, item.symbol)

    sorted_events = sorted(events, key=_event_sort_key)
    lines = []
    for event in sorted_events:
        start_repr = event.start_at.isoformat() if event.start_at else "-"
        end_repr = event.end_at.isoformat() if event.end_at else "-"
        session_repr = event.session or "-"
        notes_repr = event.notes or "-"
        timezone_repr = event.timezone or "-"
        lines.append(
            f"{event.iso_date} | {event.symbol:<8} | session={session_repr:<8} | "
            f"start={start_repr} | end={end_repr} | tz={timezone_repr} | "
            f"source={event.source or '-'} | notes={notes_repr}"
        )
    return "\n".join(f"  {line}" for line in lines)


def apply_outputs(
    events: Sequence[EarningsEvent],
    options: RuntimeOptions,
    *,
    since: date,
    until: date,
) -> RunSummary:
    summary = RunSummary(
        since=since,
        until=until,
        events=list(events),
    )

    if not events:
        print("没拉到任何财报日。检查 API Key、代码是否美股、日期范围或数据源限额。", file=sys.stderr)

    if options.export_ics:
        logger.info("导出 ICS 文件：%s", options.export_ics)
        ics_payload = build_ics(
            events,
            prodid="-//earnings-to-calendar//",
            target_timezone=options.target_timezone,
            default_duration_minutes=options.event_duration_minutes,
        )
        with open(options.export_ics, "w", encoding="utf-8") as file_obj:
            file_obj.write(ics_payload)
        print(f"ICS 已导出：{options.export_ics}")
        summary.ics_path = options.export_ics

    if options.google_insert:
        logger.info(
            "写入 Google Calendar：calendarId=%s calendarName=%s create_if_missing=%s credentials=%s token=%s",
            options.google_calendar_id,
            options.google_calendar_name,
            options.google_create_calendar,
            options.google_credentials,
            options.google_token,
        )
        if events:
            formatted = _format_google_event_lines(events, options)
            logger.info("Google Calendar 待写入事件（%d 条）：\n%s", len(events), formatted)
        else:
            logger.info("Google Calendar 待写入事件：0 条")
        target_calendar_id = google_insert(
            events,
            calendar_id=options.google_calendar_id,
            creds_path=options.google_credentials,
            token_path=options.google_token,
            calendar_name=options.google_calendar_name,
            create_if_missing=options.google_create_calendar,
            target_timezone=options.target_timezone,
            default_duration_minutes=options.event_duration_minutes,
        )
        print(f"已写入 Google Calendar: {target_calendar_id}")
        summary.google_calendar_id = target_calendar_id

    if options.icloud_insert:
        if not (options.icloud_id and options.icloud_app_pass):
            raise RuntimeError("iCloud 需要 --icloud-id 与 --icloud-app-pass")
        logger.info("写入 iCloud Calendar：calendar=Earnings")
        icloud_caldav_insert(events, options.icloud_id, options.icloud_app_pass)
        print("已写入 iCloud Calendar: Earnings")
        summary.icloud_calendar_name = "Earnings"

    return summary


def run(options: RuntimeOptions, *, today: date | None = None) -> RunSummary:
    start_date = today or date.today()
    end_date = start_date + timedelta(days=options.days)
    events = collect_events(options, since=start_date, until=end_date)
    return apply_outputs(events, options, since=start_date, until=end_date)


__all__ = ["RunSummary", "apply_outputs", "collect_events", "run"]
