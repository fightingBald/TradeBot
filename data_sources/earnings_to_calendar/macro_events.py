"""Macro economic events integration via FMP economic calendar."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Iterable, List, Sequence

import requests
from zoneinfo import ZoneInfo

from .defaults import (
    DEFAULT_EVENT_DURATION_MINUTES,
    DEFAULT_TIMEOUT_SECONDS,
    USER_AGENT,
)
from .domain import EarningsEvent
from .logging_utils import get_logger
from .settings import RuntimeOptions

logger = get_logger()

FMP_ECONOMIC_URL = "https://financialmodelingprep.com/stable/economic-calendar"


@dataclass(frozen=True)
class MacroRule:
    label: str
    session: str
    patterns: Sequence[str]


def _default_rules() -> List[MacroRule]:
    return [
        MacroRule(
            "FOMC",
            "FOMC",
            ("fomc", "fed interest rate decision", "federal reserve interest rate"),
        ),
        MacroRule("ECB", "ECB", ("ecb", "european central bank")),
        MacroRule("BOE", "BOE", ("boe", "bank of england")),
        MacroRule("BOJ", "BOJ", ("boj", "bank of japan")),
        MacroRule("CPI", "CPI", ("consumer price index", "cpi")),
        MacroRule("PPI", "PPI", ("producer price index", "ppi")),
        MacroRule("NFP", "NFP", ("nonfarm payroll", "non-farm payroll", "nfp")),
        MacroRule("Retail Sales", "RETAIL", ("retail sales",)),
        MacroRule(
            "ISM",
            "ISM",
            (
                "ism manufacturing",
                "ism non-manufacturing",
                "ism services",
                "ism manufacturing pmi",
                "ism services pmi",
            ),
        ),
        MacroRule(
            "Treasury",
            "TREASURY",
            (
                "treasury auction",
                "bond auction",
                "note auction",
                "bill auction",
                "cash management bill",
                "refinancing",
                "reopening",
            ),
        ),
    ]


def _select_rules(custom_keywords: List[str]) -> List[MacroRule]:
    base_rules = _default_rules()
    if not custom_keywords:
        return base_rules

    tokens = {token.strip().lower() for token in custom_keywords if token.strip()}
    selected: List[MacroRule] = []

    for rule in base_rules:
        label_lower = rule.label.lower()
        session_lower = rule.session.lower()
        patterns = tuple(pattern.lower() for pattern in rule.patterns)
        if any(
            token == label_lower
            or token == session_lower
            or any(token in pattern for pattern in patterns)
            for token in tokens
        ):
            selected.append(rule)

    for token in tokens:
        if any(
            token == rule.label.lower()
            or token == rule.session.lower()
            or any(token in pattern for pattern in rule.patterns)
            for rule in selected
        ):
            continue
        selected.append(MacroRule(token.upper(), token.upper(), (token,)))

    return selected if selected else base_rules


def _slugify(text: str) -> str:
    slug = re.sub(r"[^A-Z0-9]+", "-", text.upper()).strip("-")
    return slug or "MACRO"


def _parse_event_datetime(
    raw: str | None, tz: ZoneInfo
) -> tuple[date | None, datetime | None]:
    if not raw:
        return None, None
    text = raw.strip()
    if not text:
        return None, None
    normalized = text.replace(" ", "T")
    dt_obj: datetime | None = None
    try:
        dt_obj = datetime.fromisoformat(normalized)
    except ValueError:
        cleaned = normalized[:19]
        try:
            dt_obj = datetime.strptime(cleaned, "%Y-%m-%dT%H:%M:%S")
        except ValueError:
            try:
                parsed_date = date.fromisoformat(text[:10])
                return parsed_date, None
            except ValueError:
                return None, None
    if dt_obj is None:
        return None, None
    if dt_obj.tzinfo is None:
        dt_obj = dt_obj.replace(tzinfo=tz)
    else:
        dt_obj = dt_obj.astimezone(tz)
    return dt_obj.date(), dt_obj


def _build_notes(item: dict) -> str:
    parts: List[str] = []
    country = item.get("country")
    if country:
        parts.append(f"Country: {country}")
    for label in ("actual", "forecast", "previous"):
        value = item.get(label)
        if value not in (None, ""):
            parts.append(f"{label.capitalize()}: {value}")
    importance = item.get("importance") or item.get("impact")
    if importance:
        parts.append(f"Importance: {importance}")
    return "; ".join(parts) if parts else "Macro event from FMP economic calendar"


def fetch_macro_events(
    start: date, end: date, options: RuntimeOptions
) -> List[EarningsEvent]:
    api_key = os.getenv("FMP_API_KEY")
    if not api_key:
        logger.error("缺少 FMP_API_KEY，无法拉取宏观经济事件")
        raise RuntimeError("缺少 FMP_API_KEY")

    params = {
        "from": start.strftime("%Y-%m-%d"),
        "to": end.strftime("%Y-%m-%d"),
        "apikey": api_key,
    }
    try:
        response = requests.get(
            FMP_ECONOMIC_URL,
            params=params,
            headers={"User-Agent": USER_AGENT},
            timeout=DEFAULT_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        payload = response.json()
    except Exception as exc:  # pragma: no cover - network/runtime
        logger.error("拉取宏观经济事件失败：%s", exc)
        raise

    if not isinstance(payload, Iterable):
        logger.warning("宏观经济事件响应格式异常：%s", type(payload))
        return []

    tz = ZoneInfo(options.source_timezone)
    duration = timedelta(
        minutes=options.event_duration_minutes or DEFAULT_EVENT_DURATION_MINUTES
    )
    rules = _select_rules(options.macro_event_keywords)
    events: List[EarningsEvent] = []

    for item in payload:
        if not isinstance(item, dict):
            continue
        event_name = str(item.get("event") or "").strip()
        if not event_name:
            continue
        lower_name = event_name.lower()
        matched_rule = None
        for rule in rules:
            if any(pattern in lower_name for pattern in rule.patterns):
                matched_rule = rule
                break
        if matched_rule is None:
            continue

        event_date, start_at = _parse_event_datetime(item.get("date"), tz)
        if event_date is None:
            try:
                event_date = date.fromisoformat(item.get("date", "")[:10])
            except ValueError:
                logger.debug("无法解析宏观事件日期：%s", item.get("date"))
                continue

        if start_at is not None:
            end_at = start_at + duration
        else:
            end_at = None

        symbol = f"MACRO-{_slugify(event_name)}"
        notes = _build_notes(item)

        events.append(
            EarningsEvent(
                symbol=symbol,
                date=event_date,
                session=matched_rule.session,
                source="FMP-Economic",
                notes=notes,
                start_at=start_at,
                end_at=end_at,
                timezone=tz.key if start_at is not None else tz.key,
            )
        )

    return events


__all__ = ["fetch_macro_events"]
