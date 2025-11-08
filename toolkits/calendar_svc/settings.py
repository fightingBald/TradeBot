"""Runtime configuration helpers for earnings-to-calendar."""

from __future__ import annotations

import argparse
import json
import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping

from .defaults import (
    DEFAULT_EVENT_DURATION_MINUTES,
    DEFAULT_LOOKAHEAD_DAYS,
    DEFAULT_SESSION_TIMES,
    DEFAULT_SOURCE_TIMEZONE,
    DEFAULT_TARGET_TIMEZONE,
)
from .logging_utils import get_logger

logger = get_logger()

_DEFAULT_SOURCE = "fmp"
_DEFAULT_GOOGLE_CREDENTIALS = "credentials.json"
_DEFAULT_GOOGLE_TOKEN = "token.json"
_DEFAULT_ENV_FILE = ".env"
_DEFAULT_SYNC_STATE = ".cache/earnings_sync.json"

CONFIG_TEMPLATE = """# Earnings → Calendar CLI defaults (TOML)

# 需要抓取的股票列表，可随时注释/调整
symbols = ["AAPL", "MSFT", "NVDA"]

# 数据来源 (fmp 或 finnhub)
source = "fmp"

# 查询天数（今天起算）
days = 120

# 来源与目标时区设置（IANA 时区名）
source_timezone = "America/New_York"
target_timezone = "America/New_York"

# 若日历要使用定时事件，可调整时长（单位：分钟）
event_duration_minutes = 60

# 是否添加市场事件（四巫日 / OPEX / VIX）
market_events = false

# 是否添加宏观事件（FOMC / CPI / NFP 等）
macro_events = false
macro_event_source = "benzinga"
macro_event_keywords = ["FOMC", "ECB", "BOE", "BOJ", "CPI", "PPI", "NFP", "Retail Sales", "ISM", "Treasury"]

# 增量同步（仅对 Google Calendar 生效）
incremental_sync = false
sync_state_path = ".cache/earnings_sync.json"

# 会话时间映射，可根据需要覆盖（BMO=盘前, AMC=盘后）
[session_times]
BMO = "08:00"
AMC = "17:00"
"""

_ENV_KEY_GOOGLE_CREDENTIALS = "GOOGLE_CREDENTIALS_PATH"
_ENV_KEY_GOOGLE_TOKEN = "GOOGLE_TOKEN_PATH"
_ENV_KEY_GOOGLE_INSERT = "GOOGLE_INSERT"
_ENV_KEY_GOOGLE_CALENDAR_ID = "GOOGLE_CALENDAR_ID"
_ENV_KEY_GOOGLE_CALENDAR_NAME = "GOOGLE_CALENDAR_NAME"
_ENV_KEY_GOOGLE_CREATE_CAL = "GOOGLE_CREATE_CALENDAR"
_ENV_KEY_SOURCE_TZ = "SOURCE_TIMEZONE"
_ENV_KEY_TARGET_TZ = "TARGET_TIMEZONE"
_ENV_KEY_EVENT_DURATION = "EVENT_DURATION_MINUTES"
_ENV_KEY_MARKET_EVENTS = "MARKET_EVENTS"
_ENV_KEY_SESSION_TIMES = "SESSION_TIMES"
_ENV_KEY_ICLOUD_INSERT = "ICLOUD_INSERT"
_ENV_KEY_ICLOUD_ID = "ICLOUD_APPLE_ID"
_ENV_KEY_ICLOUD_APP_PASS = "ICLOUD_APP_PASSWORD"
_ENV_KEY_MACRO_EVENTS = "MACRO_EVENTS"
_ENV_KEY_MACRO_KEYWORDS = "MACRO_EVENT_KEYWORDS"
_ENV_KEY_MACRO_SOURCE = "MACRO_EVENT_SOURCE"
_ENV_KEY_INCREMENTAL_SYNC = "INCREMENTAL_SYNC"
_ENV_KEY_SYNC_STATE_PATH = "SYNC_STATE_PATH"


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
    source_timezone: str
    target_timezone: str
    event_duration_minutes: int
    session_time_map: Dict[str, str]
    market_events: bool
    icloud_insert: bool
    icloud_id: str | None
    icloud_app_pass: str | None
    macro_events: bool = False
    macro_event_keywords: List[str] = field(default_factory=list)
    macro_event_source: str = "benzinga"
    incremental_sync: bool = False
    sync_state_path: str | None = None


def parse_symbols(raw: Iterable[str]) -> List[str]:
    """Normalize a list of ticker inputs."""
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


def load_env_file(path: str | None, *, search_root: Path | None = None) -> None:
    """Load environment variables from a `.env`-style file."""
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
    logger.debug(
        "未找到可用的环境变量文件，候选路径：%s", ", ".join(str(c) for c in candidates)
    )


def load_config(
    config_path: str | None, default_path: Path | None = None
) -> tuple[Dict[str, Any], Path | None]:
    """Read CLI configuration from TOML or JSON."""
    cfg_path: Path | None = None
    create_template = False
    if config_path:
        cfg_path = Path(config_path)
    elif default_path:
        cfg_path = default_path
        create_template = True

    if cfg_path is None:
        logger.debug("未指定配置文件，返回空配置")
        return {}, None

    if not cfg_path.exists():
        if create_template:
            cfg_path.parent.mkdir(parents=True, exist_ok=True)
            cfg_path.write_text(CONFIG_TEMPLATE, encoding="utf-8")
            logger.info("已生成默认配置文件：%s", cfg_path)
        else:
            raise RuntimeError(f"找不到配置文件：{cfg_path}")

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
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"配置文件解析失败：{config_path}") from exc
    except tomllib.TOMLDecodeError as exc:
        raise RuntimeError(f"配置文件解析失败：{config_path}") from exc


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


def _coerce_symbols(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return parse_symbols(value.split(","))
    if isinstance(value, Iterable):
        return parse_symbols(value)
    raise ValueError("symbols 配置必须是字符串或字符串列表")


def _coerce_str_list(value: Any) -> List[str]:
    if value is None:
        return []
    if isinstance(value, str):
        items = [item.strip() for item in value.split(",")]
        return [item for item in items if item]
    if isinstance(value, Iterable):
        return [str(item).strip() for item in value if str(item).strip()]
    raise ValueError("宏观事件关键词必须是字符串或字符串列表")


def _parse_session_times(value: Any, default: Dict[str, str]) -> Dict[str, str]:
    if value is None:
        return {k.upper(): v for k, v in default.items()}
    if isinstance(value, dict):
        return {str(k).upper(): str(v) for k, v in value.items()}
    if isinstance(value, str):
        entries: Dict[str, str] = {}
        for part in value.split(","):
            if "=" not in part:
                continue
            key, time_str = part.split("=", 1)
            key = key.strip().upper()
            time_str = time_str.strip()
            if key and time_str:
                entries[key] = time_str
        if entries:
            return entries
        raise ValueError("session_times 字符串需形如 BMO=08:00,AMC=17:00")
    raise ValueError("session_times 必须是对象或逗号分隔的 k=v 字符串")


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


def build_runtime_options(
    parsed: argparse.Namespace,
    config: Mapping[str, Any],
    *,
    config_base: Path | None,
    project_root: Path,
) -> RuntimeOptions:
    symbols: List[str] = []
    if getattr(parsed, "symbols", None):
        symbols = parse_symbols(str(parsed.symbols).split(","))
    elif "symbols" in config:
        symbols = _coerce_symbols(config.get("symbols"))
    if not symbols:
        raise ValueError("请至少提供一个有效的股票代码。")

    source = str(parsed.source or config.get("source") or _DEFAULT_SOURCE)

    if getattr(parsed, "days", None) is not None:
        days = int(parsed.days)
    elif "days" in config:
        days = _coerce_int(config.get("days"), field="days")
    else:
        days = DEFAULT_LOOKAHEAD_DAYS

    export_ics = getattr(parsed, "export_ics", None) or config.get("export_ics")

    env_google_credentials = os.getenv(_ENV_KEY_GOOGLE_CREDENTIALS)
    raw_google_credentials = (
        getattr(parsed, "google_credentials", None)
        or config.get("google_credentials")
        or env_google_credentials
        or _DEFAULT_GOOGLE_CREDENTIALS
    )
    google_credentials = _resolve_path(
        raw_google_credentials, base=config_base, root=project_root
    )

    env_google_token = os.getenv(_ENV_KEY_GOOGLE_TOKEN)
    raw_google_token = (
        getattr(parsed, "google_token", None)
        or config.get("google_token")
        or env_google_token
        or _DEFAULT_GOOGLE_TOKEN
    )
    google_token = _resolve_path(raw_google_token, base=config_base, root=project_root)

    raw_calendar_id = (
        getattr(parsed, "google_calendar_id", None)
        or config.get("google_calendar_id")
        or os.getenv(_ENV_KEY_GOOGLE_CALENDAR_ID)
    )
    google_calendar_id = str(raw_calendar_id) if raw_calendar_id else None

    google_calendar_name = (
        getattr(parsed, "google_calendar_name", None)
        or config.get("google_calendar_name")
        or os.getenv(_ENV_KEY_GOOGLE_CALENDAR_NAME)
    )
    if google_calendar_name:
        google_calendar_name = str(google_calendar_name)

    if not google_calendar_id and not google_calendar_name:
        google_calendar_id = "primary"

    if getattr(parsed, "google_create_calendar", False):
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
            google_create_calendar = (
                env_create_flag if env_create_flag is not None else False
            )

    source_timezone = (
        getattr(parsed, "source_tz", None)
        or config.get("source_timezone")
        or os.getenv(_ENV_KEY_SOURCE_TZ)
        or DEFAULT_SOURCE_TIMEZONE
    )

    target_timezone = (
        getattr(parsed, "target_tz", None)
        or config.get("target_timezone")
        or os.getenv(_ENV_KEY_TARGET_TZ)
        or DEFAULT_TARGET_TIMEZONE
    )

    if getattr(parsed, "event_duration", None) is not None:
        event_duration = int(parsed.event_duration)
    elif "event_duration_minutes" in config:
        event_duration = _coerce_int(
            config.get("event_duration_minutes"), field="event_duration_minutes"
        )
    else:
        event_duration = int(
            os.getenv(_ENV_KEY_EVENT_DURATION) or DEFAULT_EVENT_DURATION_MINUTES
        )
    if event_duration <= 0:
        raise ValueError("event_duration_minutes 必须为正整数")

    session_time_map = _parse_session_times(
        getattr(parsed, "session_times", None)
        or config.get("session_times")
        or os.getenv(_ENV_KEY_SESSION_TIMES),
        default=DEFAULT_SESSION_TIMES,
    )

    if getattr(parsed, "market_events", None):
        market_events = True
    else:
        config_market_events = (
            _coerce_bool(config.get("market_events"))
            if "market_events" in config
            else None
        )
        if config_market_events is not None:
            market_events = config_market_events
        else:
            env_market_events = _coerce_bool(os.getenv(_ENV_KEY_MARKET_EVENTS))
            market_events = (
                env_market_events if env_market_events is not None else False
            )

    if getattr(parsed, "google_insert", None):
        google_insert = True
    else:
        google_insert = False
        config_google_insert = (
            _coerce_bool(config.get("google_insert"))
            if "google_insert" in config
            else None
        )
        if config_google_insert is not None:
            google_insert = config_google_insert
        else:
            env_google_insert = _coerce_bool(os.getenv(_ENV_KEY_GOOGLE_INSERT))
            if env_google_insert is not None:
                google_insert = env_google_insert

    if getattr(parsed, "icloud_insert", None):
        icloud_insert = True
    else:
        icloud_insert = False
        config_icloud_insert = (
            _coerce_bool(config.get("icloud_insert"))
            if "icloud_insert" in config
            else None
        )
        if config_icloud_insert is not None:
            icloud_insert = config_icloud_insert
        else:
            env_icloud_insert = _coerce_bool(os.getenv(_ENV_KEY_ICLOUD_INSERT))
            if env_icloud_insert is not None:
                icloud_insert = env_icloud_insert

    icloud_id = (
        getattr(parsed, "icloud_id", None)
        or config.get("icloud_id")
        or os.getenv(_ENV_KEY_ICLOUD_ID)
    )
    icloud_app_pass = (
        getattr(parsed, "icloud_app_pass", None)
        or config.get("icloud_app_pass")
        or os.getenv(_ENV_KEY_ICLOUD_APP_PASS)
    )

    if getattr(parsed, "macro_events", None):
        macro_events = True
    else:
        config_macro_events = (
            _coerce_bool(config.get("macro_events"))
            if "macro_events" in config
            else None
        )
        if config_macro_events is not None:
            macro_events = config_macro_events
        else:
            env_macro_events = _coerce_bool(os.getenv(_ENV_KEY_MACRO_EVENTS))
            macro_events = env_macro_events if env_macro_events is not None else False

    raw_macro_keywords = (
        getattr(parsed, "macro_event_keywords", None)
        or config.get("macro_event_keywords")
        or os.getenv(_ENV_KEY_MACRO_KEYWORDS)
    )
    macro_event_keywords = _coerce_str_list(raw_macro_keywords)

    raw_macro_source = (
        getattr(parsed, "macro_event_source", None)
        or config.get("macro_event_source")
        or os.getenv(_ENV_KEY_MACRO_SOURCE)
    )
    macro_event_source = (
        str(raw_macro_source).strip().lower() if raw_macro_source else "benzinga"
    )
    if macro_event_source != "benzinga":
        raise ValueError("macro_event_source 目前仅支持 benzinga")

    incremental_sync = bool(getattr(parsed, "incremental", False))
    if not incremental_sync:
        config_incremental = (
            _coerce_bool(config.get("incremental_sync"))
            if "incremental_sync" in config
            else None
        )
        if config_incremental is not None:
            incremental_sync = config_incremental
        else:
            env_incremental = _coerce_bool(os.getenv(_ENV_KEY_INCREMENTAL_SYNC))
            incremental_sync = env_incremental if env_incremental is not None else False

    raw_sync_state_path = (
        getattr(parsed, "sync_state_path", None)
        or config.get("sync_state_path")
        or os.getenv(_ENV_KEY_SYNC_STATE_PATH)
    )
    if not raw_sync_state_path and incremental_sync:
        raw_sync_state_path = _DEFAULT_SYNC_STATE
    sync_state_path = (
        _resolve_path(raw_sync_state_path, base=config_base, root=project_root)
        if raw_sync_state_path
        else None
    )

    options = RuntimeOptions(
        symbols=symbols,
        source=source,
        days=days,
        export_ics=export_ics,
        google_insert=google_insert,
        google_credentials=str(google_credentials),
        google_token=str(google_token),
        google_calendar_id=(
            str(google_calendar_id) if google_calendar_id is not None else None
        ),
        google_calendar_name=google_calendar_name,
        google_create_calendar=google_create_calendar,
        source_timezone=str(source_timezone),
        target_timezone=str(target_timezone),
        event_duration_minutes=event_duration,
        session_time_map=session_time_map,
        market_events=market_events,
        icloud_insert=icloud_insert,
        icloud_id=str(icloud_id) if icloud_id is not None else None,
        icloud_app_pass=str(icloud_app_pass) if icloud_app_pass is not None else None,
        macro_events=macro_events,
        macro_event_keywords=macro_event_keywords,
        macro_event_source=macro_event_source,
        incremental_sync=incremental_sync,
        sync_state_path=str(sync_state_path) if sync_state_path is not None else None,
    )

    return options


__all__ = [
    "RuntimeOptions",
    "build_runtime_options",
    "load_config",
    "load_env_file",
    "parse_symbols",
]
