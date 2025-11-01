"""Command line interface for earnings-to-calendar."""

from __future__ import annotations

import argparse
import json
import tomllib
import os
import sys
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Sequence

import logging

from .calendars import build_ics, google_insert, icloud_caldav_insert
from .config import DEFAULT_LOOKAHEAD_DAYS
from .domain import deduplicate_events
from .logging_utils import LOGGER_NAME, get_logger
from .providers import PROVIDERS, EarningsDataProvider

_DEFAULT_SOURCE = "fmp"
_DEFAULT_GOOGLE_CREDENTIALS = "credentials.json"
_DEFAULT_GOOGLE_TOKEN = "token.json"
_DEFAULT_ENV_FILE = ".env"

_ENV_KEY_GOOGLE_CREDENTIALS = "GOOGLE_CREDENTIALS_PATH"
_ENV_KEY_GOOGLE_TOKEN = "GOOGLE_TOKEN_PATH"
_ENV_KEY_GOOGLE_INSERT = "GOOGLE_INSERT"
_ENV_KEY_GOOGLE_CALENDAR_ID = "GOOGLE_CALENDAR_ID"
_ENV_KEY_GOOGLE_CALENDAR_NAME = "GOOGLE_CALENDAR_NAME"
_ENV_KEY_GOOGLE_CREATE_CAL = "GOOGLE_CREATE_CALENDAR"
_ENV_KEY_ICLOUD_INSERT = "ICLOUD_INSERT"
_ENV_KEY_ICLOUD_ID = "ICLOUD_APPLE_ID"
_ENV_KEY_ICLOUD_APP_PASS = "ICLOUD_APP_PASSWORD"

logger = get_logger()


@dataclass
class RuntimeOptions:
    symbols: List[str]
    source: str
    days: int
    export_ics: str | None
    google_insert: bool
    google_credentials: str
    google_token: str
    google_calendar_id: str | None
    google_calendar_name: str | None
    google_create_calendar: bool
    icloud_insert: bool
    icloud_id: str | None
    icloud_app_pass: str | None


def _resolve_provider(source: str) -> EarningsDataProvider:
    if source not in PROVIDERS:
        raise ValueError(f"Unsupported data source: {source}")
    env_var = "FMP_API_KEY" if source == "fmp" else "FINNHUB_API_KEY"
    api_key = os.getenv(env_var)
    if not api_key:
        logger.error("环境变量 %s 未配置，无法使用数据源 %s", env_var, source)
    return PROVIDERS[source](api_key)


def _parse_symbols(raw: Iterable[str]) -> List[str]:
    symbols: List[str] = []
    for token in raw:
        piece = token.strip().upper()
        if piece and piece not in symbols:
            symbols.append(piece)
    return symbols


def _read_env_file(env_path: Path) -> None:
    logger.debug("Loading environment variables from %s", env_path)
    try:
        with env_path.open("r", encoding="utf-8") as handle:
            for raw_line in handle:
                line = raw_line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                key = key.strip()
                if not key:
                    continue
                cleaned = value.strip().strip('"').strip("'")
                os.environ.setdefault(key, cleaned)
    except OSError as exc:
        raise RuntimeError(f"无法读取环境文件：{env_path}") from exc


def _load_env_file(path: str | None, *, search_root: Path | None = None) -> None:
    env_path = Path(path) if path else Path(_DEFAULT_ENV_FILE)
    candidates = [env_path]
    if not env_path.is_absolute():
        root = search_root or Path(__file__).resolve().parents[2]
        candidates.append(root / env_path)

    for candidate in candidates:
        if candidate.exists():
            _read_env_file(candidate)
            logger.info("已加载环境变量文件：%s", candidate)
            return
    logger.debug("未找到可用的环境变量文件，候选路径：%s", ", ".join(str(c) for c in candidates))


def _load_config(config_path: str | None, default_path: Path | None = None) -> tuple[Dict[str, Any], Path | None]:
    target_path: Path | None = None
    if config_path:
        target_path = Path(config_path)
    elif default_path and default_path.exists():
        target_path = default_path

    if target_path is None:
        logger.debug("未指定配置文件，返回空配置")
        return {}, None

    cfg_path = target_path
    try:
        if cfg_path.suffix.lower() == ".toml":
            with cfg_path.open("rb") as handle:
                data = tomllib.load(handle)
        else:
            with cfg_path.open("r", encoding="utf-8") as handle:
                data = json.load(handle)
        if not isinstance(data, Mapping):
            raise ValueError("配置文件必须是对象/表结构")
        logger.info("已加载配置文件：%s", cfg_path)
        return dict(data), cfg_path.parent
    except FileNotFoundError as exc:
        raise RuntimeError(f"找不到配置文件：{config_path}") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"配置文件解析失败：{config_path}") from exc
    except tomllib.TOMLDecodeError as exc:
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


def _coerce_bool(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "y", "on"}:
            return True
        if normalized in {"0", "false", "no", "n", "off"}:
            return False
    raise ValueError("布尔配置必须是 true/false 或 1/0")


def _resolve_path(value: Any, *, base: Path | None, root: Path) -> str | None:
    if value is None:
        return None
    text = str(value)
    if not text:
        return None
    path = Path(text)
    if path.is_absolute():
        return str(path)
    candidates: list[Path] = []
    if base is not None:
        candidates.append(base / path)
    candidates.append(root / path)
    candidates.append(Path.cwd() / path)
    for candidate in candidates:
        parent = candidate.parent
        if candidate.exists() or parent.exists():
            logger.debug("解析路径 %s -> %s", value, candidate)
            return str(candidate)
    logger.debug("路径 %s 未找到对应文件，默认取 %s", value, candidates[0])
    return str(candidates[0])


def _build_runtime_options(
    parsed: argparse.Namespace,
    config: Mapping[str, Any],
    *,
    config_base: Path | None,
    project_root: Path,
) -> RuntimeOptions:
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

    env_google_credentials = os.getenv(_ENV_KEY_GOOGLE_CREDENTIALS)
    raw_google_credentials = (
        parsed.google_credentials
        or config.get("google_credentials")
        or env_google_credentials
        or _DEFAULT_GOOGLE_CREDENTIALS
    )
    google_credentials = _resolve_path(
        raw_google_credentials, base=config_base, root=project_root
    )

    env_google_token = os.getenv(_ENV_KEY_GOOGLE_TOKEN)
    raw_google_token = (
        parsed.google_token
        or config.get("google_token")
        or env_google_token
        or _DEFAULT_GOOGLE_TOKEN
    )
    google_token = _resolve_path(raw_google_token, base=config_base, root=project_root)

    raw_calendar_id = (
        parsed.google_calendar_id
        or config.get("google_calendar_id")
        or os.getenv(_ENV_KEY_GOOGLE_CALENDAR_ID)
    )
    google_calendar_id = str(raw_calendar_id) if raw_calendar_id else None

    google_calendar_name = (
        parsed.google_calendar_name
        or config.get("google_calendar_name")
        or os.getenv(_ENV_KEY_GOOGLE_CALENDAR_NAME)
    )
    if google_calendar_name:
        google_calendar_name = str(google_calendar_name)

    if not google_calendar_id and not google_calendar_name:
        google_calendar_id = "primary"

    if parsed.google_create_calendar:
        google_create_calendar = True
    else:
        config_create_flag = (
            _coerce_bool(config.get("google_create_calendar"))
            if "google_create_calendar" in config
            else None
        )
        if config_create_flag is not None:
            google_create_calendar = config_create_flag
        else:
            env_create_flag = _coerce_bool(os.getenv(_ENV_KEY_GOOGLE_CREATE_CAL))
            google_create_calendar = env_create_flag if env_create_flag is not None else False

    if parsed.google_insert:
        google_insert = True
    else:
        google_insert = False
        config_google_insert = _coerce_bool(config.get("google_insert")) if "google_insert" in config else None
        if config_google_insert is not None:
            google_insert = config_google_insert
        else:
            env_google_insert = _coerce_bool(os.getenv(_ENV_KEY_GOOGLE_INSERT))
            if env_google_insert is not None:
                google_insert = env_google_insert

    if parsed.icloud_insert:
        icloud_insert = True
    else:
        icloud_insert = False
        config_icloud_insert = _coerce_bool(config.get("icloud_insert")) if "icloud_insert" in config else None
        if config_icloud_insert is not None:
            icloud_insert = config_icloud_insert
        else:
            env_icloud_insert = _coerce_bool(os.getenv(_ENV_KEY_ICLOUD_INSERT))
            if env_icloud_insert is not None:
                icloud_insert = env_icloud_insert

    icloud_id = parsed.icloud_id or config.get("icloud_id") or os.getenv(_ENV_KEY_ICLOUD_ID)
    icloud_app_pass = parsed.icloud_app_pass or config.get("icloud_app_pass") or os.getenv(
        _ENV_KEY_ICLOUD_APP_PASS
    )

    return RuntimeOptions(
        symbols=symbols,
        source=source,
        days=days,
        export_ics=export_ics,
        google_insert=google_insert,
        google_credentials=str(google_credentials),
        google_token=str(google_token),
        google_calendar_id=str(google_calendar_id) if google_calendar_id is not None else None,
        google_calendar_name=google_calendar_name,
        google_create_calendar=google_create_calendar,
        icloud_insert=icloud_insert,
        icloud_id=str(icloud_id) if icloud_id is not None else None,
        icloud_app_pass=str(icloud_app_pass) if icloud_app_pass is not None else None,
    )


def main(args: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Earnings → Calendar")
    parser.add_argument("--env-file", help="Path to .env file with environment variables.")
    parser.add_argument("--config", help="Path to JSON config file with default options.")
    parser.add_argument("--symbols", help="Comma separated tickers, e.g. AAPL,MSFT,NVDA")
    parser.add_argument("--source", choices=list(PROVIDERS.keys()))
    parser.add_argument("--days", type=int)
    parser.add_argument("--export-ics", metavar="PATH", help="Export ICS file")
    parser.add_argument("--google-insert", action="store_true", help="Insert events into Google Calendar")
    parser.add_argument("--google-credentials", help="Path to Google OAuth credentials.json")
    parser.add_argument("--google-token", help="Path to stored Google OAuth token.json")
    parser.add_argument("--google-calendar-id", help="Target Google calendarId (default: primary)")
    parser.add_argument("--google-calendar-name", help="Target Google calendar name (used when ID missing)")
    parser.add_argument("--google-create-calendar", action="store_true", help="Create Google Calendar when name not found")
    parser.add_argument("--icloud-insert", action="store_true", help="Insert to iCloud via CalDAV")
    parser.add_argument("--icloud-id")
    parser.add_argument("--icloud-app-pass")
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"],
        help="Logging verbosity (default: INFO).",
    )
    parsed = parser.parse_args(args=args)

    logging.basicConfig(
        level=getattr(logging, parsed.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    logger.debug("Logger initialized with level %s", parsed.log_level.upper())

    project_root = Path(__file__).resolve().parents[2]

    _load_env_file(parsed.env_file, search_root=project_root)

    default_config_path = project_root / "config" / "earnings_to_calendar.toml"
    config_data, config_base = _load_config(parsed.config, default_path=default_config_path)

    try:
        options = _build_runtime_options(
            parsed,
            config_data,
            config_base=config_base,
            project_root=project_root,
        )
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)

    since = date.today()
    until = since + timedelta(days=options.days)

    provider = _resolve_provider(options.source)
    logger.info(
        "开始拉取数据：source=%s symbols=%s 窗口=%s~%s",
        options.source,
        ",".join(options.symbols),
        since,
        until,
    )
    events = provider.fetch(options.symbols, since, until)
    unique_events = deduplicate_events(events)
    logger.info("共获取事件 %d 条（去重后 %d 条）", len(events), len(unique_events))

    if not unique_events:
        print("没拉到任何财报日。检查 API Key、代码是否美股、日期范围或数据源限额。", file=sys.stderr)

    if options.export_ics:
        logger.info("导出 ICS 文件：%s", options.export_ics)
        ics_payload = build_ics(unique_events)
        with open(options.export_ics, "w", encoding="utf-8") as file_obj:
            file_obj.write(ics_payload)
        print(f"ICS 已导出：{options.export_ics}")

    if options.google_insert:
        logger.info(
            "写入 Google Calendar：calendarId=%s calendarName=%s create_if_missing=%s credentials=%s token=%s",
            options.google_calendar_id,
            options.google_calendar_name,
            options.google_create_calendar,
            options.google_credentials,
            options.google_token,
        )
        target_calendar_id = google_insert(
            unique_events,
            calendar_id=options.google_calendar_id,
            creds_path=options.google_credentials,
            token_path=options.google_token,
            calendar_name=options.google_calendar_name,
            create_if_missing=options.google_create_calendar,
        )
        print(f"已写入 Google Calendar: {target_calendar_id}")

    if options.icloud_insert:
        if not (options.icloud_id and options.icloud_app_pass):
            raise RuntimeError("iCloud 需要 --icloud-id 与 --icloud-app-pass")
        logger.info("写入 iCloud Calendar：calendar=Earnings")
        icloud_caldav_insert(unique_events, options.icloud_id, options.icloud_app_pass)
        print("已写入 iCloud Calendar: Earnings")
