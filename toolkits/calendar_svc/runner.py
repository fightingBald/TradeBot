"""High-level orchestration helpers for earnings-to-calendar."""

from __future__ import annotations

import os
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from .calendars import GoogleCalendarConfig, build_ics, google_insert, icloud_caldav_insert
from .domain import EarningsEvent, deduplicate_events
from .logging_utils import get_logger
from .macro_events import fetch_macro_events
from .market_events import generate_market_events
from .providers import PROVIDERS, EarningsDataProvider
from .settings import RuntimeOptions
from .sync_state import SyncDiff, build_sync_state, diff_events, load_sync_state, save_sync_state

logger = get_logger()


@dataclass(slots=True)
class RunSummary:
    since: date
    until: date
    events: list[EarningsEvent]
    google_calendar_id: str | None = None
    ics_path: str | None = None
    icloud_calendar_name: str | None = None
    sync_stats: dict[str, int] | None = None


@dataclass(slots=True)
class DateWindow:
    """Inclusive date range for the pipeline run."""

    since: date
    until: date


def _resolve_provider(options: RuntimeOptions, *, source_override: str | None = None) -> EarningsDataProvider:
    source = source_override or options.source
    if source not in PROVIDERS:
        raise ValueError(f"Unsupported data source: {source}")
    env_var = "FMP_API_KEY" if source == "fmp" else "FINNHUB_API_KEY"
    api_key = os.getenv(env_var)
    if not api_key:
        logger.error("环境变量 %s 未配置，无法使用数据源 %s", env_var, source)
        raise RuntimeError(f"缺少 {env_var}")

    provider_cls = PROVIDERS[source]
    return provider_cls(
        api_key,
        source_timezone=options.source_timezone,
        session_times=options.session_time_map,
        event_duration_minutes=options.event_duration_minutes,
    )


def collect_events(options: RuntimeOptions, *, since: date, until: date) -> list[EarningsEvent]:
    provider = _resolve_provider(options)
    logger.info(
        "开始拉取数据：source=%s symbols=%s 窗口=%s~%s", options.source, ",".join(options.symbols), since, until
    )
    events = provider.fetch(options.symbols, since, until)
    collected_symbols = {event.symbol for event in events}
    missing = [symbol for symbol in options.symbols if symbol not in collected_symbols]

    if missing and options.fallback_source:
        logger.info(
            "主数据源 %s 缺少 %d 个符号，尝试后备数据源 %s：%s",
            options.source,
            len(missing),
            options.fallback_source,
            ",".join(missing),
        )
        fallback_provider = _resolve_provider(options, source_override=options.fallback_source)
        fallback_events = fallback_provider.fetch(missing, since, until)
        events.extend(fallback_events)
        collected_symbols.update(event.symbol for event in fallback_events)
        missing = [symbol for symbol in options.symbols if symbol not in collected_symbols]

    if missing:
        logger.warning("仍缺少 %d 个符号的财报日期：%s", len(missing), ",".join(missing))
    if options.market_events:
        extras = generate_market_events(since, until, options)
        if extras:
            logger.info("追加市场事件 %d 条", len(extras))
            events.extend(extras)
    if options.macro_events:
        try:
            macro_events = fetch_macro_events(since, until, options)
        except Exception as exc:  # pragma: no cover - network failure surfaces to logs
            logger.error("获取宏观事件失败，将继续处理基础财报事件：%s", exc)
            macro_events = []
        if macro_events:
            logger.info("追加宏观事件 %d 条", len(macro_events))
            events.extend(macro_events)
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
    lines = [f"{event.iso_date} | {event.symbol}" for event in sorted_events]
    return "\n".join(f"  {line}" for line in lines)


def _build_sync_stats(sync_diff: SyncDiff, total: int) -> dict[str, int]:
    return {
        "created": len(sync_diff.to_create),
        "updated": len(sync_diff.to_update),
        "skipped": len(sync_diff.unchanged),
        "total": total,
    }


def _apply_ics_output(options: RuntimeOptions, events: Sequence[EarningsEvent], summary: RunSummary) -> None:
    if not options.export_ics:
        return
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


def _apply_google_output(
    options: RuntimeOptions,
    *,
    events_for_google: Sequence[EarningsEvent],
    sync_diff: SyncDiff | None,
    summary: RunSummary,
    total_events: int,
) -> None:
    if not options.google_insert:
        if sync_diff is not None:
            summary.sync_stats = _build_sync_stats(sync_diff, total_events)
        return

    logger.info(
        "写入 Google Calendar：calendarId=%s calendarName=%s create_if_missing=%s credentials=%s token=%s",
        options.google_calendar_id,
        options.google_calendar_name,
        options.google_create_calendar,
        options.google_credentials,
        options.google_token,
    )
    if sync_diff is not None:
        summary.sync_stats = _build_sync_stats(sync_diff, total_events)
        logger.info(
            "增量同步统计：create=%d update=%d skip=%d total=%d",
            summary.sync_stats["created"],
            summary.sync_stats["updated"],
            summary.sync_stats["skipped"],
            summary.sync_stats["total"],
        )
    if events_for_google:
        formatted = _format_google_event_lines(events_for_google, options)
        logger.info("Google Calendar 待写入事件（%d 条）：\n%s", len(events_for_google), formatted)
        target_calendar_id = google_insert(
            events_for_google,
            config=GoogleCalendarConfig(
                calendar_id=options.google_calendar_id,
                creds_path=options.google_credentials,
                token_path=options.google_token,
                calendar_name=options.google_calendar_name,
                create_if_missing=options.google_create_calendar,
                target_timezone=options.target_timezone,
                default_duration_minutes=options.event_duration_minutes,
            ),
        )
        print(f"已写入 Google Calendar: {target_calendar_id}")
        summary.google_calendar_id = target_calendar_id
    else:
        logger.info("增量同步无需写入 Google Calendar（无变动）")
        if summary.sync_stats is None:
            summary.sync_stats = {"created": 0, "updated": 0, "skipped": total_events, "total": total_events}


def _apply_icloud_output(options: RuntimeOptions, events: Sequence[EarningsEvent], summary: RunSummary) -> None:
    if not options.icloud_insert:
        return
    if not (options.icloud_id and options.icloud_app_pass):
        raise RuntimeError("iCloud 需要 --icloud-id 与 --icloud-app-pass")
    logger.info("写入 iCloud Calendar：calendar=Earnings")
    icloud_caldav_insert(events, options.icloud_id, options.icloud_app_pass)
    print("已写入 iCloud Calendar: Earnings")
    summary.icloud_calendar_name = "Earnings"


def apply_outputs(
    events: Sequence[EarningsEvent],
    options: RuntimeOptions,
    *,
    window: DateWindow,
    events_for_google: Sequence[EarningsEvent],
    sync_diff: SyncDiff | None = None,
) -> RunSummary:
    summary = RunSummary(since=window.since, until=window.until, events=list(events))

    if not events:
        print("没拉到任何财报日。检查 API Key、代码是否美股、日期范围或数据源限额。", file=sys.stderr)

    _apply_ics_output(options, events, summary)
    _apply_google_output(
        options,
        events_for_google=events_for_google,
        sync_diff=sync_diff,
        summary=summary,
        total_events=len(events),
    )
    _apply_icloud_output(options, events, summary)

    return summary


def run(options: RuntimeOptions, *, today: date | None = None) -> RunSummary:
    start_date = today or datetime.now(UTC).date()
    end_date = start_date + timedelta(days=options.days)
    events = collect_events(options, since=start_date, until=end_date)
    sync_diff: SyncDiff | None = None
    events_for_google: Sequence[EarningsEvent] = events
    if options.incremental_sync and options.sync_state_path:
        state = load_sync_state(options.sync_state_path)
        sync_diff = diff_events(events, state)
        events_for_google = [*sync_diff.to_create, *sync_diff.to_update]
    summary = apply_outputs(
        events,
        options,
        window=DateWindow(since=start_date, until=end_date),
        events_for_google=events_for_google,
        sync_diff=sync_diff,
    )
    if options.incremental_sync and options.sync_state_path:
        fingerprints = sync_diff.fingerprints if sync_diff else {}
        new_state = build_sync_state(events, fingerprints, since=start_date, until=end_date)
        save_sync_state(options.sync_state_path, new_state)
        if summary.sync_stats is None and sync_diff is not None:
            summary.sync_stats = {
                "created": len(sync_diff.to_create),
                "updated": len(sync_diff.to_update),
                "skipped": len(sync_diff.unchanged),
                "total": len(events),
            }
    return summary


__all__ = ["RunSummary", "DateWindow", "apply_outputs", "collect_events", "run"]
