"""Public interface for earnings-to-calendar utilities."""

from .calendars import build_ics, google_insert, icloud_caldav_insert
from .cli import main
from .defaults import DEFAULT_LOOKAHEAD_DAYS, DEFAULT_TIMEOUT_SECONDS, USER_AGENT
from .domain import EarningsEvent, deduplicate_events, parse_iso_date
from .providers import (
    EarningsDataProvider,
    FinnhubEarningsProvider,
    FmpEarningsProvider,
    PROVIDERS,
)
from .macro_events import fetch_macro_events
from .runner import RunSummary, apply_outputs, collect_events, run
from .settings import RuntimeOptions, build_runtime_options, load_config, load_env_file, parse_symbols

_parse_symbols = parse_symbols  # backward compatibility

__all__ = [
    "DEFAULT_LOOKAHEAD_DAYS",
    "DEFAULT_TIMEOUT_SECONDS",
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
    "google_insert",
    "icloud_caldav_insert",
    "load_config",
    "load_env_file",
    "main",
    "parse_iso_date",
    "parse_symbols",
    "run",
    "RuntimeOptions",
    "_parse_symbols",
]
