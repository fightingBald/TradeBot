"""Public interface for earnings-to-calendar utilities."""

from .calendars import build_ics, google_insert, icloud_caldav_insert
from .defaults import (
    DEFAULT_EVENT_DURATION_MINUTES,
    DEFAULT_LOOKAHEAD_DAYS,
    DEFAULT_SESSION_TIMES,
    DEFAULT_SOURCE_TIMEZONE,
    DEFAULT_TARGET_TIMEZONE,
    DEFAULT_TIMEOUT_SECONDS,
    USER_AGENT,
)
from .domain import EarningsEvent, deduplicate_events, parse_iso_date
from .macro_events import _slugify, fetch_macro_events
from .market_events import generate_market_events
from .providers import (
    PROVIDERS,
    EarningsDataProvider,
    FinnhubEarningsProvider,
    FmpEarningsProvider,
)
from .runner import RunSummary, apply_outputs, collect_events, run
from .settings import (
    RuntimeOptions,
    build_runtime_options,
    load_config,
    load_env_file,
    parse_symbols,
)
from .sync_state import (
    SyncDiff,
    build_sync_state,
    diff_events,
    load_sync_state,
    save_sync_state,
)

_parse_symbols = parse_symbols  # backward compatibility

__all__ = [
    "DEFAULT_LOOKAHEAD_DAYS",
    "DEFAULT_TIMEOUT_SECONDS",
    "DEFAULT_EVENT_DURATION_MINUTES",
    "DEFAULT_SESSION_TIMES",
    "DEFAULT_SOURCE_TIMEZONE",
    "DEFAULT_TARGET_TIMEZONE",
    "USER_AGENT",
    "EarningsEvent",
    "EarningsDataProvider",
    "FmpEarningsProvider",
    "FinnhubEarningsProvider",
    "PROVIDERS",
    "RunSummary",
    "apply_outputs",
    "build_ics",
    "build_runtime_options",
    "collect_events",
    "deduplicate_events",
    "fetch_macro_events",
    "_slugify",
    "generate_market_events",
    "google_insert",
    "icloud_caldav_insert",
    "load_config",
    "load_env_file",
    "parse_iso_date",
    "parse_symbols",
    "run",
    "RuntimeOptions",
    "_parse_symbols",
    "build_sync_state",
    "diff_events",
    "load_sync_state",
    "save_sync_state",
    "SyncDiff",
]
