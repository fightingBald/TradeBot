"""Public interface for earnings-to-calendar utilities."""

from .calendars import build_ics, google_insert, icloud_caldav_insert
from .cli import RuntimeOptions, _parse_symbols, main
from .defaults import DEFAULT_LOOKAHEAD_DAYS, DEFAULT_TIMEOUT_SECONDS, USER_AGENT
from .domain import EarningsEvent, deduplicate_events, parse_iso_date
from .providers import (
    EarningsDataProvider,
    FinnhubEarningsProvider,
    FmpEarningsProvider,
    PROVIDERS,
)

__all__ = [
    "DEFAULT_LOOKAHEAD_DAYS",
    "DEFAULT_TIMEOUT_SECONDS",
    "USER_AGENT",
    "EarningsEvent",
    "EarningsDataProvider",
    "FmpEarningsProvider",
    "FinnhubEarningsProvider",
    "PROVIDERS",
    "build_ics",
    "google_insert",
    "icloud_caldav_insert",
    "deduplicate_events",
    "parse_iso_date",
    "RuntimeOptions",
    "_parse_symbols",
    "main",
]
