"""Runtime configuration helpers for earnings-to-calendar."""

from __future__ import annotations

import argparse
import json
import os
import tomllib
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

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
# 当主数据源缺失符号时，可设置后备数据源 (fmp/finnhub)
# fallback_source = "finnhub"

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
_ENV_KEY_FALLBACK_SOURCE = "FALLBACK_SOURCE"


@dataclass
class RuntimeOptions:
    symbols: list[str]
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
    session_time_map: dict[str, str]
    market_events: bool
    icloud_insert: bool
    icloud_id: str | None
    icloud_app_pass: str | None
    macro_events: bool = False
    macro_event_keywords: list[str] = field(default_factory=list)
    macro_event_source: str = "benzinga"
    incremental_sync: bool = False
    sync_state_path: str | None = None
    fallback_source: str | None = None


def parse_symbols(raw: Iterable[str]) -> list[str]:
    """Normalize a list of ticker inputs."""
    symbols: list[str] = []
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
    logger.debug("未找到可用的环境变量文件，候选路径：%s", ", ".join(str(c) for c in candidates))


def load_config(config_path: str | None, default_path: Path | None = None) -> tuple[dict[str, Any], Path | None]:
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


def _coerce_symbols(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return parse_symbols(value.split(","))
    if isinstance(value, Iterable):
        return parse_symbols(value)
    raise ValueError("symbols 配置必须是字符串或字符串列表")


def _coerce_str_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        items = [item.strip() for item in value.split(",")]
        return [item for item in items if item]
    if isinstance(value, Iterable):
        return [str(item).strip() for item in value if str(item).strip()]
    raise ValueError("宏观事件关键词必须是字符串或字符串列表")


def _parse_session_times(value: Any, default: dict[str, str]) -> dict[str, str]:
    if value is None:
        return {k.upper(): v for k, v in default.items()}
    if isinstance(value, dict):
        return {str(k).upper(): str(v) for k, v in value.items()}
    if isinstance(value, str):
        entries: dict[str, str] = {}
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


@dataclass(slots=True)
class _ResolverContext:
    parsed: argparse.Namespace
    config: Mapping[str, Any]


@dataclass(slots=True)
class _GoogleOptions:
    credentials: str
    token: str
    calendar_id: str | None
    calendar_name: str | None
    create_if_missing: bool


def _resolve_symbols_arg(ctx: _ResolverContext) -> list[str]:
    if getattr(ctx.parsed, "symbols", None):
        return parse_symbols(str(ctx.parsed.symbols).split(","))
    if "symbols" in ctx.config:
        return _coerce_symbols(ctx.config.get("symbols"))
    raise ValueError("请至少提供一个有效的股票代码。")


def _resolve_days(ctx: _ResolverContext) -> int:
    if getattr(ctx.parsed, "days", None) is not None:
        return int(ctx.parsed.days)
    if "days" in ctx.config:
        return _coerce_int(ctx.config.get("days"), field="days")
    return DEFAULT_LOOKAHEAD_DAYS


def _resolve_flag(
    ctx: _ResolverContext, attr: str, *, config_key: str, env_key: str | None = None, default: bool = False
) -> bool:
    if getattr(ctx.parsed, attr, False):
        return True
    config_val = _coerce_bool(ctx.config.get(config_key)) if config_key in ctx.config else None
    if config_val is not None:
        return config_val
    if env_key:
        env_val = _coerce_bool(os.getenv(env_key))
        if env_val is not None:
            return env_val
    return default


def _resolve_optional_str(
    ctx: _ResolverContext, attr: str, *, config_key: str | None = None, env_key: str | None = None
) -> str | None:
    candidates = [
        getattr(ctx.parsed, attr, None),
        ctx.config.get(config_key) if config_key else None,
        os.getenv(env_key) if env_key else None,
    ]
    for candidate in candidates:
        if candidate in (None, ""):
            continue
        return str(candidate)
    return None


def _resolve_google_options(ctx: _ResolverContext, *, config_base: Path | None, project_root: Path) -> _GoogleOptions:
    raw_google_credentials = (
        getattr(ctx.parsed, "google_credentials", None)
        or ctx.config.get("google_credentials")
        or os.getenv(_ENV_KEY_GOOGLE_CREDENTIALS)
        or _DEFAULT_GOOGLE_CREDENTIALS
    )
    google_credentials = _resolve_path(raw_google_credentials, base=config_base, root=project_root)

    raw_google_token = (
        getattr(ctx.parsed, "google_token", None)
        or ctx.config.get("google_token")
        or os.getenv(_ENV_KEY_GOOGLE_TOKEN)
        or _DEFAULT_GOOGLE_TOKEN
    )
    google_token = _resolve_path(raw_google_token, base=config_base, root=project_root)

    calendar_id = _resolve_optional_str(
        ctx, "google_calendar_id", config_key="google_calendar_id", env_key=_ENV_KEY_GOOGLE_CALENDAR_ID
    )
    calendar_name = _resolve_optional_str(
        ctx, "google_calendar_name", config_key="google_calendar_name", env_key=_ENV_KEY_GOOGLE_CALENDAR_NAME
    )
    if not calendar_id and not calendar_name:
        calendar_id = "primary"

    google_create_calendar = _resolve_flag(
        ctx,
        "google_create_calendar",
        config_key="google_create_calendar",
        env_key=_ENV_KEY_GOOGLE_CREATE_CAL,
        default=False,
    )

    return _GoogleOptions(
        credentials=str(google_credentials),
        token=str(google_token),
        calendar_id=calendar_id,
        calendar_name=calendar_name,
        create_if_missing=google_create_calendar,
    )


def _resolve_timezone(ctx: _ResolverContext, attr: str, *, config_key: str, env_key: str, default: str) -> str:
    value = getattr(ctx.parsed, attr, None) or ctx.config.get(config_key) or os.getenv(env_key) or default
    return str(value)


def _resolve_event_duration(ctx: _ResolverContext) -> int:
    if getattr(ctx.parsed, "event_duration", None) is not None:
        event_duration = int(ctx.parsed.event_duration)
    elif "event_duration_minutes" in ctx.config:
        event_duration = _coerce_int(ctx.config.get("event_duration_minutes"), field="event_duration_minutes")
    else:
        env_duration = os.getenv(_ENV_KEY_EVENT_DURATION)
        event_duration = int(env_duration) if env_duration not in (None, "") else DEFAULT_EVENT_DURATION_MINUTES
    if event_duration <= 0:
        raise ValueError("event_duration_minutes 必须为正整数")
    return event_duration


def _resolve_macro_keywords(ctx: _ResolverContext) -> list[str]:
    raw_macro_keywords = (
        getattr(ctx.parsed, "macro_event_keywords", None)
        or ctx.config.get("macro_event_keywords")
        or os.getenv(_ENV_KEY_MACRO_KEYWORDS)
    )
    return _coerce_str_list(raw_macro_keywords)


def _resolve_macro_source(ctx: _ResolverContext) -> str:
    raw_macro_source = (
        getattr(ctx.parsed, "macro_event_source", None)
        or ctx.config.get("macro_event_source")
        or os.getenv(_ENV_KEY_MACRO_SOURCE)
    )
    macro_event_source = str(raw_macro_source).strip().lower() if raw_macro_source else "benzinga"
    if macro_event_source != "benzinga":
        raise ValueError("macro_event_source 目前仅支持 benzinga")
    return macro_event_source


def _resolve_fallback_source(ctx: _ResolverContext, primary_source: str) -> str | None:
    raw = (
        getattr(ctx.parsed, "fallback_source", None)
        or ctx.config.get("fallback_source")
        or os.getenv(_ENV_KEY_FALLBACK_SOURCE)
    )
    if raw in (None, ""):
        return None
    value = str(raw).strip().lower()
    if value not in {"fmp", "finnhub"}:
        raise ValueError("fallback_source 目前仅支持 fmp 或 finnhub")
    if value == primary_source:
        raise ValueError("fallback_source 不可与主数据源相同")
    return value


def _resolve_primary_inputs(ctx: _ResolverContext) -> tuple[list[str], str, int, str | None]:
    symbols = _resolve_symbols_arg(ctx)
    source = str(getattr(ctx.parsed, "source", None) or ctx.config.get("source") or _DEFAULT_SOURCE)
    days = _resolve_days(ctx)
    export_ics = getattr(ctx.parsed, "export_ics", None) or ctx.config.get("export_ics")
    return symbols, source, days, export_ics


def _resolve_time_settings(
    ctx: _ResolverContext,
    *,
    config_base: Path | None,
    project_root: Path,
) -> tuple[_GoogleOptions, str, str, int, dict[str, str]]:
    google_opts = _resolve_google_options(ctx, config_base=config_base, project_root=project_root)
    source_timezone = _resolve_timezone(
        ctx, "source_tz", config_key="source_timezone", env_key=_ENV_KEY_SOURCE_TZ, default=DEFAULT_SOURCE_TIMEZONE
    )
    target_timezone = _resolve_timezone(
        ctx, "target_tz", config_key="target_timezone", env_key=_ENV_KEY_TARGET_TZ, default=DEFAULT_TARGET_TIMEZONE
    )
    event_duration = _resolve_event_duration(ctx)
    session_time_map = _parse_session_times(
        getattr(ctx.parsed, "session_times", None) or ctx.config.get("session_times") or os.getenv(_ENV_KEY_SESSION_TIMES),
        default=DEFAULT_SESSION_TIMES,
    )
    return google_opts, str(source_timezone), str(target_timezone), event_duration, session_time_map


def _resolve_delivery_flags(ctx: _ResolverContext) -> tuple[bool, bool, bool]:
    market_events = _resolve_flag(
        ctx, "market_events", config_key="market_events", env_key=_ENV_KEY_MARKET_EVENTS, default=False
    )
    google_insert = _resolve_flag(
        ctx, "google_insert", config_key="google_insert", env_key=_ENV_KEY_GOOGLE_INSERT, default=False
    )
    icloud_insert = _resolve_flag(
        ctx, "icloud_insert", config_key="icloud_insert", env_key=_ENV_KEY_ICLOUD_INSERT, default=False
    )
    return market_events, google_insert, icloud_insert


def _resolve_icloud_options(ctx: _ResolverContext) -> tuple[str | None, str | None]:
    icloud_id = _resolve_optional_str(ctx, "icloud_id", config_key="icloud_id", env_key=_ENV_KEY_ICLOUD_ID)
    icloud_app_pass = _resolve_optional_str(
        ctx, "icloud_app_pass", config_key="icloud_app_pass", env_key=_ENV_KEY_ICLOUD_APP_PASS
    )
    return icloud_id, icloud_app_pass


def _resolve_macro_options(ctx: _ResolverContext, primary_source: str) -> tuple[bool, list[str], str, str | None]:
    macro_events = _resolve_flag(
        ctx, "macro_events", config_key="macro_events", env_key=_ENV_KEY_MACRO_EVENTS, default=False
    )
    macro_event_keywords = _resolve_macro_keywords(ctx)
    macro_event_source = _resolve_macro_source(ctx)
    fallback_source = _resolve_fallback_source(ctx, primary_source)
    return macro_events, macro_event_keywords, macro_event_source, fallback_source


def _resolve_sync_state(
    ctx: _ResolverContext,
    *,
    config_base: Path | None,
    project_root: Path,
) -> tuple[bool, str | None]:
    incremental_sync = _resolve_flag(
        ctx, "incremental", config_key="incremental_sync", env_key=_ENV_KEY_INCREMENTAL_SYNC, default=False
    )
    raw_sync_state_path = _resolve_optional_str(
        ctx, "sync_state_path", config_key="sync_state_path", env_key=_ENV_KEY_SYNC_STATE_PATH
    )
    if incremental_sync and not raw_sync_state_path:
        raw_sync_state_path = _DEFAULT_SYNC_STATE
    sync_state_path = (
        _resolve_path(raw_sync_state_path, base=config_base, root=project_root) if raw_sync_state_path else None
    )
    return incremental_sync, str(sync_state_path) if sync_state_path is not None else None


def build_runtime_options(
    parsed: argparse.Namespace, config: Mapping[str, Any], *, config_base: Path | None, project_root: Path
) -> RuntimeOptions:
    ctx = _ResolverContext(parsed=parsed, config=config)

    symbols, source, days, export_ics = _resolve_primary_inputs(ctx)
    google_opts, source_timezone, target_timezone, event_duration, session_time_map = _resolve_time_settings(
        ctx, config_base=config_base, project_root=project_root
    )
    market_events, google_insert, icloud_insert = _resolve_delivery_flags(ctx)
    icloud_id, icloud_app_pass = _resolve_icloud_options(ctx)
    macro_events, macro_event_keywords, macro_event_source, fallback_source = _resolve_macro_options(ctx, source)
    incremental_sync, sync_state_path = _resolve_sync_state(ctx, config_base=config_base, project_root=project_root)

    options = RuntimeOptions(
        symbols=symbols,
        source=source,
        days=days,
        export_ics=export_ics,
        google_insert=google_insert,
        google_credentials=google_opts.credentials,
        google_token=google_opts.token,
        google_calendar_id=google_opts.calendar_id,
        google_calendar_name=google_opts.calendar_name,
        google_create_calendar=google_opts.create_if_missing,
        source_timezone=source_timezone,
        target_timezone=target_timezone,
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
        sync_state_path=sync_state_path,
        fallback_source=fallback_source,
    )

    return options


__all__ = ["RuntimeOptions", "build_runtime_options", "load_config", "load_env_file", "parse_symbols"]
