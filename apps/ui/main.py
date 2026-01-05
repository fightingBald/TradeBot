from __future__ import annotations

import logging
from datetime import UTC, datetime

import streamlit as st
from pydantic import ValidationError

from apps.ui.api_client import (
    ApiError,
    fetch_bars,
    fetch_positions,
    fetch_profile,
    fetch_quotes,
    fetch_trades,
    fetch_watchlist,
)
from apps.ui.settings import UiSettings
from apps.ui.transformers import bars_to_frame, market_snapshots_to_frame, positions_to_frame
from apps.ui.views import render_candles, render_kill_switch, render_market_watch, render_positions

logger = logging.getLogger(__name__)

CONFIRM_LIVE = "LIVE"
CONFIRM_PAPER = "PAPER"


def _configure_logging() -> None:
    root_logger = logging.getLogger()
    if root_logger.handlers:
        return
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


def _load_settings() -> UiSettings:
    try:
        return UiSettings()
    except ValidationError as exc:
        logger.exception("Failed to load UI settings")
        st.error("Missing UI settings. Check .env or environment variables.")
        st.code(str(exc))
        st.stop()


def _update_positions(settings: UiSettings) -> None:
    try:
        st.session_state["positions"] = fetch_positions(settings.api_base_url, settings.profile_id)
        st.session_state["positions_last_refresh"] = datetime.now(UTC)
    except ApiError as exc:
        st.error(str(exc))
        st.stop()


def _update_watchlist(settings: UiSettings) -> None:
    try:
        st.session_state["watchlist"] = fetch_watchlist(settings.api_base_url, settings.profile_id)
    except ApiError as exc:
        st.error(str(exc))
        st.stop()


def _update_market_snapshots(settings: UiSettings, symbols: list[str]) -> None:
    try:
        st.session_state["market_quotes"] = fetch_quotes(settings.api_base_url, settings.profile_id, symbols)
        st.session_state["market_trades"] = fetch_trades(settings.api_base_url, settings.profile_id, symbols)
        st.session_state["market_last_refresh"] = datetime.now(UTC)
    except ApiError as exc:
        st.error(str(exc))
        st.stop()


def _update_market_bars(settings: UiSettings, symbol: str) -> None:
    try:
        bars = fetch_bars(
            settings.api_base_url,
            settings.profile_id,
            [symbol],
            limit=settings.marketdata_bars_limit,
            timeframe=settings.marketdata_timeframe,
        )
        st.session_state["market_bars"] = bars.get(symbol, [])
        st.session_state["market_bars_symbol"] = symbol
    except ApiError as exc:
        st.error(str(exc))
        st.stop()


def _render_sidebar(environment: str, profile_id: str, api_base_url: str) -> None:
    st.sidebar.header("Trading Profile")
    if environment == "live":
        st.sidebar.error(f"ENV: {environment}")
    else:
        st.sidebar.success(f"ENV: {environment}")
    st.sidebar.text(f"Profile ID: {profile_id}")
    st.sidebar.text(f"API: {api_base_url}")


def _render_market_data(settings: UiSettings) -> None:
    st.header("Market Data")

    if "watchlist" not in st.session_state:
        _update_watchlist(settings)

    watchlist = st.session_state.get("watchlist", [])
    if not watchlist:
        st.info("Watchlist is empty. Set MARKETDATA_SYMBOLS and start market data daemon.")
        return

    selected_symbol = st.selectbox("Symbol", watchlist, key="market_symbol")

    if "market_quotes" not in st.session_state:
        _update_market_snapshots(settings, watchlist)

    if st.button("Refresh market data"):
        _update_market_snapshots(settings, watchlist)
        _update_market_bars(settings, selected_symbol)

    last_refresh = st.session_state.get("market_last_refresh")
    if last_refresh:
        st.caption(f"Market data last refresh: {last_refresh.isoformat()}")

    market_df = market_snapshots_to_frame(
        st.session_state.get("market_quotes", {}),
        st.session_state.get("market_trades", {}),
    )
    render_market_watch(market_df)

    if selected_symbol:
        if st.session_state.get("market_bars_symbol") != selected_symbol:
            _update_market_bars(settings, selected_symbol)
        bars_df = bars_to_frame(st.session_state.get("market_bars", []))
        render_candles(bars_df, symbol=selected_symbol, timeframe=settings.marketdata_timeframe)


def main() -> None:
    _configure_logging()
    st.set_page_config(page_title="Alpaca Positions Dashboard", layout="wide")
    st.title("Alpaca Positions Dashboard")

    settings = _load_settings()

    try:
        profile = fetch_profile(settings.api_base_url, settings.profile_id)
    except ApiError as exc:
        st.error(str(exc))
        st.stop()

    environment = profile.get("environment", "paper")
    confirm_phrase = CONFIRM_LIVE if environment == "live" else CONFIRM_PAPER

    profile_id = profile.get("profile_id", settings.profile_id)
    _render_sidebar(environment, profile_id, settings.api_base_url)

    if "positions" not in st.session_state:
        _update_positions(settings)

    if st.button("Refresh positions"):
        _update_positions(settings)

    last_refresh = st.session_state.get("positions_last_refresh")
    if last_refresh:
        st.caption(f"Last refresh: {last_refresh.isoformat()}")

    df = positions_to_frame(st.session_state["positions"])
    render_positions(df)

    st.divider()
    _render_market_data(settings)

    st.divider()
    command_id = render_kill_switch(settings.api_base_url, settings.profile_id, confirm_phrase)
    if command_id:
        st.session_state["positions"] = []
        st.session_state["positions_last_refresh"] = datetime.now(UTC)


if __name__ == "__main__":
    main()
