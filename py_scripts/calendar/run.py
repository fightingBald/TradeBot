"""Command line entry point for the calendar pipeline."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import Sequence

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
LIB_DIR = ROOT / "lib"
if LIB_DIR.exists() and str(LIB_DIR) not in sys.path:
    sys.path.insert(0, str(LIB_DIR))

from lib.calendar_svc.logging_utils import get_logger  # noqa: E402
from lib.calendar_svc.runner import run  # noqa: E402
from lib.calendar_svc.settings import (  # noqa: E402
    build_runtime_options,
    load_config,
    load_env_file,
)

logger = get_logger()


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Earnings → Calendar")
    parser.add_argument(
        "--env-file", help="Path to .env file with environment variables."
    )
    parser.add_argument(
        "--config", help="Path to JSON/TOML config file with default options."
    )
    parser.add_argument(
        "--symbols", help="Comma separated tickers, e.g. AAPL,MSFT,NVDA"
    )
    parser.add_argument("--source", help="Data source name (fmp/finnhub)")
    parser.add_argument("--days", type=int)
    parser.add_argument("--export-ics", metavar="PATH", help="Export ICS file")
    parser.add_argument(
        "--google-insert",
        action="store_true",
        help="Insert events into Google Calendar",
    )
    parser.add_argument(
        "--google-credentials", help="Path to Google OAuth credentials.json"
    )
    parser.add_argument("--google-token", help="Path to stored Google OAuth token.json")
    parser.add_argument(
        "--google-calendar-id", help="Target Google calendarId (default: primary)"
    )
    parser.add_argument(
        "--google-calendar-name",
        help="Target Google calendar name (used when ID missing)",
    )
    parser.add_argument(
        "--google-create-calendar",
        action="store_true",
        help="Create Google Calendar when name not found",
    )
    parser.add_argument(
        "--source-tz", help="Timezone of source data (e.g. America/New_York)"
    )
    parser.add_argument(
        "--target-tz", help="Timezone for calendar output (e.g. Europe/Berlin)"
    )
    parser.add_argument(
        "--event-duration", type=int, help="Duration (minutes) for timed events"
    )
    parser.add_argument(
        "--session-times", help="Override session times, e.g. BMO=08:00,AMC=17:00"
    )
    parser.add_argument(
        "--market-events",
        action="store_true",
        help="Include major market calendar events",
    )
    parser.add_argument(
        "--macro-events",
        action="store_true",
        help="Include macro economic events (FOMC/CPI/etc)",
    )
    parser.add_argument(
        "--macro-event-keywords",
        help="Comma separated macro event keywords to filter, e.g. FOMC,CPI,NFP",
    )
    parser.add_argument(
        "--macro-event-source",
        choices=["benzinga"],
        help="Macro economic data provider (only Benzinga is supported).",
    )
    parser.add_argument(
        "--incremental",
        action="store_true",
        help="Enable incremental Google Calendar sync",
    )
    parser.add_argument(
        "--sync-state-path", help="Path to incremental sync state JSON cache"
    )
    parser.add_argument(
        "--icloud-insert", action="store_true", help="Insert to iCloud via CalDAV"
    )
    parser.add_argument("--icloud-id")
    parser.add_argument("--icloud-app-pass")
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"],
        help="Logging verbosity (default: INFO).",
    )
    return parser


def main(args: Sequence[str] | None = None) -> None:
    parser = _build_parser()
    parsed = parser.parse_args(args=args)

    logging.basicConfig(
        level=getattr(logging, parsed.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    logger.debug("Logger initialized with level %s", parsed.log_level.upper())

    project_root = ROOT

    load_env_file(parsed.env_file, search_root=project_root)

    default_config_path = project_root / "config" / "events_to_google_calendar.toml"
    config_data, config_base = load_config(
        parsed.config, default_path=default_config_path
    )

    try:
        options = build_runtime_options(
            parsed,
            config_data,
            config_base=config_base,
            project_root=project_root,
        )
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)

    run(options)


if __name__ == "__main__":
    main()
