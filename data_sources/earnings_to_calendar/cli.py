"""Command line interface for earnings-to-calendar."""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Dict, Iterable, List, Mapping, Sequence

from .calendars import build_ics, google_insert, icloud_caldav_insert
from .config import DEFAULT_LOOKAHEAD_DAYS
from .domain import deduplicate_events
from .providers import PROVIDERS, EarningsDataProvider

_DEFAULT_SOURCE = "fmp"
_DEFAULT_GOOGLE_CREDENTIALS = "credentials.json"
_DEFAULT_GOOGLE_TOKEN = "token.json"


@dataclass
class RuntimeOptions:
    symbols: List[str]
    source: str
    days: int
    export_ics: str | None
    google_insert: bool
    google_credentials: str
    google_token: str
    icloud_insert: bool
    icloud_id: str | None
    icloud_app_pass: str | None


def _resolve_provider(source: str) -> EarningsDataProvider:
    if source not in PROVIDERS:
        raise ValueError(f"Unsupported data source: {source}")
    env_var = "FMP_API_KEY" if source == "fmp" else "FINNHUB_API_KEY"
    api_key = os.getenv(env_var)
    return PROVIDERS[source](api_key)


def _parse_symbols(raw: Iterable[str]) -> List[str]:
    symbols: List[str] = []
    for token in raw:
        piece = token.strip().upper()
        if piece and piece not in symbols:
            symbols.append(piece)
    return symbols


def _load_config(config_path: str | None) -> Dict[str, Any]:
    if not config_path:
        return {}
    try:
        with open(config_path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
            if not isinstance(data, Mapping):
                raise ValueError("配置文件必须是 JSON 对象")
            return dict(data)
    except FileNotFoundError as exc:
        raise RuntimeError(f"找不到配置文件：{config_path}") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"配置文件解析失败：{config_path}") from exc


def _coerce_symbols(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return _parse_symbols(value.split(","))
    if isinstance(value, Iterable):
        return _parse_symbols(value)
    raise ValueError("symbols 配置必须是字符串或字符串列表")


def _coerce_int(value: Any, *, field: str) -> int:
    if value is None:
        raise ValueError(f"{field} 配置缺失")
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip():
        try:
            return int(value.strip())
        except ValueError as exc:
            raise ValueError(f"{field} 配置必须是整数") from exc
    raise ValueError(f"{field} 配置必须是整数")


def _build_runtime_options(parsed: argparse.Namespace, config: Mapping[str, Any]) -> RuntimeOptions:
    symbols = []
    if parsed.symbols:
        symbols = _parse_symbols(parsed.symbols.split(","))
    elif "symbols" in config:
        symbols = _coerce_symbols(config.get("symbols"))
    if not symbols:
        raise ValueError("请至少提供一个有效的股票代码。")

    if parsed.source:
        source = parsed.source
    else:
        source = str(config.get("source") or _DEFAULT_SOURCE)

    if parsed.days is not None:
        days = parsed.days
    elif "days" in config:
        days = _coerce_int(config.get("days"), field="days")
    else:
        days = DEFAULT_LOOKAHEAD_DAYS

    export_ics = parsed.export_ics or config.get("export_ics")

    google_credentials = (
        parsed.google_credentials
        or config.get("google_credentials")
        or _DEFAULT_GOOGLE_CREDENTIALS
    )
    google_token = parsed.google_token or config.get("google_token") or _DEFAULT_GOOGLE_TOKEN

    google_insert = bool(parsed.google_insert or config.get("google_insert"))

    icloud_insert = bool(parsed.icloud_insert or config.get("icloud_insert"))
    icloud_id = parsed.icloud_id or config.get("icloud_id")
    icloud_app_pass = parsed.icloud_app_pass or config.get("icloud_app_pass")

    return RuntimeOptions(
        symbols=symbols,
        source=source,
        days=days,
        export_ics=export_ics,
        google_insert=google_insert,
        google_credentials=str(google_credentials),
        google_token=str(google_token),
        icloud_insert=icloud_insert,
        icloud_id=str(icloud_id) if icloud_id is not None else None,
        icloud_app_pass=str(icloud_app_pass) if icloud_app_pass is not None else None,
    )


def main(args: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Earnings → Calendar")
    parser.add_argument("--config", help="Path to JSON config file with default options.")
    parser.add_argument("--symbols", help="Comma separated tickers, e.g. AAPL,MSFT,NVDA")
    parser.add_argument("--source", choices=list(PROVIDERS.keys()))
    parser.add_argument("--days", type=int)
    parser.add_argument("--export-ics", metavar="PATH", help="Export ICS file")
    parser.add_argument("--google-insert", action="store_true", help="Insert to Google Calendar (primary)")
    parser.add_argument("--google-credentials", help="Path to Google OAuth credentials.json")
    parser.add_argument("--google-token", help="Path to stored Google OAuth token.json")
    parser.add_argument("--icloud-insert", action="store_true", help="Insert to iCloud via CalDAV")
    parser.add_argument("--icloud-id")
    parser.add_argument("--icloud-app-pass")
    parsed = parser.parse_args(args=args)

    config_data = _load_config(parsed.config)

    try:
        options = _build_runtime_options(parsed, config_data)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)

    since = date.today()
    until = since + timedelta(days=options.days)

    provider = _resolve_provider(options.source)
    events = provider.fetch(options.symbols, since, until)
    unique_events = deduplicate_events(events)

    if not unique_events:
        print("没拉到任何财报日。检查 API Key、代码是否美股、日期范围或数据源限额。", file=sys.stderr)

    if options.export_ics:
        ics_payload = build_ics(unique_events)
        with open(options.export_ics, "w", encoding="utf-8") as file_obj:
            file_obj.write(ics_payload)
        print(f"ICS 已导出：{options.export_ics}")

    if options.google_insert:
        google_insert(unique_events, "primary", options.google_credentials, options.google_token)
        print("已写入 Google Calendar: primary")

    if options.icloud_insert:
        if not (options.icloud_id and options.icloud_app_pass):
            raise RuntimeError("iCloud 需要 --icloud-id 与 --icloud-app-pass")
        icloud_caldav_insert(unique_events, options.icloud_id, options.icloud_app_pass)
        print("已写入 iCloud Calendar: Earnings")
