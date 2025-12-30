from __future__ import annotations

import logging
from datetime import UTC, datetime
from decimal import Decimal

import pandas as pd
import streamlit as st
from pydantic import ValidationError

from app.config import Settings
from app.models import UserPosition
from app.services.alpaca_market_data import AlpacaMarketDataService

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


def _load_settings() -> Settings:
    try:
        return Settings()
    except ValidationError as exc:
        logger.exception("Failed to load settings")
        st.error("Missing Alpaca credentials. Check .env or environment variables.")
        st.code(str(exc))
        st.stop()


def _to_float(value: Decimal | None) -> float:
    if value is None:
        return float("nan")
    return float(value)


def _positions_to_frame(positions: list[UserPosition]) -> pd.DataFrame:
    records: list[dict[str, object]] = []
    for position in positions:
        records.append(
            {
                "symbol": position.symbol,
                "side": position.side,
                "quantity": _to_float(position.quantity),
                "avg_entry_price": _to_float(position.avg_entry_price),
                "market_value": _to_float(position.market_value),
                "unrealized_pl": _to_float(position.unrealized_pl),
                "unrealized_plpc": _to_float(position.unrealized_plpc),
                "current_price": _to_float(position.current_price),
            }
        )

    df = pd.DataFrame.from_records(records)
    if df.empty:
        return df

    total_value = df["market_value"].sum()
    df["weight"] = df["market_value"] / total_value if total_value else 0.0
    df.sort_values("market_value", ascending=False, inplace=True)
    return df


def _load_positions(service: AlpacaMarketDataService) -> list[UserPosition]:
    logger.info("Fetching positions from Alpaca")
    try:
        positions = service.get_user_positions()
    except RuntimeError as exc:
        logger.exception("Failed to fetch positions")
        st.error(str(exc))
        st.stop()
    logger.info("Fetched %s positions", len(positions))
    return positions


def _render_positions(df: pd.DataFrame) -> None:
    if df.empty:
        st.info("No open positions.")
        return

    total_value = df["market_value"].sum()
    total_pl = df["unrealized_pl"].sum()
    col1, col2 = st.columns(2)
    col1.metric("Total Market Value", f"${total_value:,.2f}")
    col2.metric("Unrealized P/L", f"${total_pl:,.2f}")

    st.subheader("Position Distribution")
    chart_data = df.set_index("symbol")["market_value"]
    st.bar_chart(chart_data, height=260)

    st.subheader("Positions")
    display_df = df[
        [
            "symbol",
            "side",
            "quantity",
            "market_value",
            "weight",
            "unrealized_pl",
            "unrealized_plpc",
            "current_price",
            "avg_entry_price",
        ]
    ]
    styled = display_df.style.format(
        {
            "quantity": "{:,.2f}",
            "market_value": "${:,.2f}",
            "weight": "{:.2%}",
            "unrealized_pl": "${:,.2f}",
            "unrealized_plpc": "{:.2%}",
            "current_price": "${:,.2f}",
            "avg_entry_price": "${:,.2f}",
        }
    )
    st.dataframe(styled, use_container_width=True)


def _render_kill_switch(service: AlpacaMarketDataService, is_live: bool) -> None:
    st.header("Kill Switch")
    st.warning("This will cancel open orders and close all positions.")
    acknowledge = st.checkbox("I understand this action is irreversible.")

    confirm_phrase = CONFIRM_LIVE if is_live else CONFIRM_PAPER
    confirm_input = st.text_input(
        f"Type {confirm_phrase} to confirm",
        type="password" if is_live else "default",
    ).strip()
    confirm_ok = confirm_input.upper() == confirm_phrase

    if st.button("Execute Kill Switch", disabled=not (acknowledge and confirm_ok)):
        logger.warning("Kill switch requested (live=%s)", is_live)
        with st.spinner("Submitting close-all request..."):
            try:
                result = service.close_all_positions(cancel_orders=True)
            except RuntimeError as exc:
                logger.exception("Kill switch failed")
                st.error(str(exc))
                return

        closed_count = len(result) if isinstance(result, list) else None
        if closed_count is None:
            st.success("Kill switch executed. Check Alpaca for fills.")
        else:
            st.success(f"Kill switch executed. Close requests: {closed_count}")
        logger.warning("Kill switch executed (closed=%s)", closed_count)

        st.session_state["positions"] = []
        st.session_state["positions_last_refresh"] = datetime.now(UTC)


def main() -> None:
    _configure_logging()
    st.set_page_config(page_title="Alpaca Positions Dashboard", layout="wide")
    st.title("Alpaca Positions Dashboard")

    settings = _load_settings()
    is_live = not settings.paper_trading
    env_label = CONFIRM_LIVE if is_live else CONFIRM_PAPER

    st.sidebar.header("Trading Profile")
    if is_live:
        st.sidebar.error(f"ENV: {env_label}")
    else:
        st.sidebar.success(f"ENV: {env_label}")
    st.sidebar.text(f"Trading URL: {settings.trading_base_url}")
    st.sidebar.text(f"Data Feed: {settings.data_feed}")

    service = AlpacaMarketDataService(settings)

    if "positions" not in st.session_state:
        st.session_state["positions"] = _load_positions(service)
        st.session_state["positions_last_refresh"] = datetime.now(UTC)

    if st.button("Refresh positions"):
        st.session_state["positions"] = _load_positions(service)
        st.session_state["positions_last_refresh"] = datetime.now(UTC)

    last_refresh = st.session_state.get("positions_last_refresh")
    if last_refresh:
        st.caption(f"Last refresh: {last_refresh.isoformat()}")

    df = _positions_to_frame(st.session_state["positions"])
    _render_positions(df)

    st.divider()
    _render_kill_switch(service, is_live=is_live)


if __name__ == "__main__":
    main()
