"""Quick helper to fetch earnings for specific symbols from a single provider.

Usage:
    python py_scripts/calendar/debug_fetch.py --symbols=AVGO,ORCL --source=fmp --days=30 --env-file=.env
"""

from __future__ import annotations

import argparse
import logging
import os
from datetime import UTC, datetime, timedelta

from toolkits.calendar_svc.defaults import (
    DEFAULT_EVENT_DURATION_MINUTES,
    DEFAULT_SESSION_TIMES,
    DEFAULT_SOURCE_TIMEZONE,
    USER_AGENT,
)
from toolkits.calendar_svc.logging_utils import get_logger
from toolkits.calendar_svc.providers import PROVIDERS, EarningsDataProvider
from toolkits.calendar_svc.settings import load_env_file, parse_symbols

logger = get_logger()


def _build_provider(source: str) -> EarningsDataProvider:
    if source not in PROVIDERS:
        raise SystemExit(f"Unsupported source: {source}. Use fmp or finnhub.")
    env_var = "FMP_API_KEY" if source == "fmp" else "FINNHUB_API_KEY"
    api_key = os.getenv(env_var)
    if not api_key:
        raise SystemExit(f"Missing {env_var}. Please set it via .env or environment.")
    provider_cls = PROVIDERS[source]
    return provider_cls(
        api_key,
        source_timezone=DEFAULT_SOURCE_TIMEZONE,
        session_times=DEFAULT_SESSION_TIMES,
        event_duration_minutes=DEFAULT_EVENT_DURATION_MINUTES,
    )


def _print_events(events) -> None:
    if not events:
        logger.warning("No events returned.")
        return
    logger.info("Returned %d events:", len(events))
    for evt in events:
        session = f" ({evt.session})" if evt.session else ""
        print(f"{evt.symbol}: {evt.date}{session} source={evt.source} tz={evt.timezone}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Debug fetch earnings for specific symbols.")
    parser.add_argument("--symbols", required=True, help="Comma separated tickers, e.g. AVGO,ORCL,MSFT")
    parser.add_argument("--source", choices=["fmp", "finnhub"], default="fmp", help="Primary data source.")
    parser.add_argument("--days", type=int, default=60, help="Lookahead days from today.")
    parser.add_argument("--env-file", default=".env", help="Path to .env file with API keys.")
    parser.add_argument("--log-level", default="INFO", choices=["CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"])
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format=f"%(asctime)s %(levelname)s %(name)s %(message)s [ua={USER_AGENT}]",
    )

    load_env_file(args.env_file)

    symbols = parse_symbols(args.symbols.split(","))
    if not symbols:
        raise SystemExit("Please provide at least one symbol.")

    provider = _build_provider(args.source)
    today = datetime.now(UTC).date()
    until = today + timedelta(days=args.days)
    logger.info("Fetching %s symbols=%s window=%s~%s", args.source, ",".join(symbols), today, until)
    events = provider.fetch(symbols, today, until)
    _print_events(events)


if __name__ == "__main__":
    main()
