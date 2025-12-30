from __future__ import annotations

import logging
from collections.abc import Sequence
from datetime import UTC, datetime
from decimal import Decimal

import altair as alt
import httpx
import pandas as pd
import streamlit as st
from pydantic import ValidationError

from apps.ui.settings import UiSettings
from core.domain.position import Position

logger = logging.getLogger(__name__)

CONFIRM_LIVE = "LIVE"
CONFIRM_PAPER = "PAPER"


class ApiError(RuntimeError):
    pass


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


def _to_float(value: Decimal | None) -> float:
    if value is None:
        return float("nan")
    return float(value)


def _positions_to_frame(positions: Sequence[Position]) -> pd.DataFrame:
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

    df["exposure_value"] = df["market_value"].abs()
    total_exposure = df["exposure_value"].sum()
    df["weight"] = df["exposure_value"] / total_exposure if total_exposure else 0.0
    df.sort_values("exposure_value", ascending=False, inplace=True)
    return df


def _fetch_positions(api_base_url: str, profile_id: str) -> list[Position]:
    logger.info("Fetching positions via API")
    url = f"{api_base_url}/state/positions"
    try:
        response = httpx.get(url, params={"profile_id": profile_id}, timeout=10)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        logger.exception("Failed to fetch positions")
        raise ApiError(f"Failed to fetch positions: {exc}") from exc

    payload = response.json()
    return [Position.model_validate(item) for item in payload]


def _fetch_profile(api_base_url: str, profile_id: str) -> dict[str, str]:
    url = f"{api_base_url}/state/profile"
    try:
        response = httpx.get(url, params={"profile_id": profile_id}, timeout=10)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        logger.exception("Failed to fetch profile")
        raise ApiError(f"Failed to fetch profile: {exc}") from exc

    return response.json()


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
    if df["exposure_value"].sum() <= 0:
        st.info("No exposure data available for distribution chart.")
    else:
        chart = (
            alt.Chart(df)
            .mark_arc()
            .encode(
                theta=alt.Theta(field="exposure_value", type="quantitative"),
                color=alt.Color(field="symbol", type="nominal"),
                tooltip=[
                    alt.Tooltip(field="symbol", type="nominal"),
                    alt.Tooltip(field="market_value", type="quantitative", format=",.2f"),
                    alt.Tooltip(field="weight", type="quantitative", format=".2%"),
                ],
            )
        )
        st.altair_chart(chart, use_container_width=True)
        st.caption("Weights use absolute market value (exposure).")

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


def _render_kill_switch(api_base_url: str, profile_id: str, confirm_phrase: str) -> None:
    st.header("Kill Switch")
    st.warning("This will cancel open orders and close all positions.")
    acknowledge = st.checkbox("I understand this action is irreversible.")

    confirm_input = st.text_input(
        f"Type {confirm_phrase} to confirm",
        type="password" if confirm_phrase == CONFIRM_LIVE else "default",
    ).strip()
    confirm_ok = confirm_input.upper() == confirm_phrase

    reason = st.text_input("Reason (optional)", placeholder="e.g. risk off")

    if st.button("Execute Kill Switch", disabled=not (acknowledge and confirm_ok)):
        logger.warning("Kill switch requested (profile=%s)", profile_id)
        with st.spinner("Submitting kill switch..."):
            url = f"{api_base_url}/commands/kill-switch"
            payload = {"profile_id": profile_id, "confirm_token": confirm_input, "reason": reason}
            try:
                response = httpx.post(url, json=payload, timeout=10)
                response.raise_for_status()
            except httpx.HTTPError as exc:
                logger.exception("Kill switch failed")
                st.error(f"Kill switch failed: {exc}")
                return

        result = response.json()
        st.success(f"Kill switch submitted. Command: {result.get('command_id')}")
        st.session_state["positions"] = []
        st.session_state["positions_last_refresh"] = datetime.now(UTC)


def main() -> None:
    _configure_logging()
    st.set_page_config(page_title="Alpaca Positions Dashboard", layout="wide")
    st.title("Alpaca Positions Dashboard")

    settings = _load_settings()

    try:
        profile = _fetch_profile(settings.api_base_url, settings.profile_id)
    except ApiError as exc:
        st.error(str(exc))
        st.stop()

    environment = profile.get("environment", "paper")
    confirm_phrase = CONFIRM_LIVE if environment == "live" else CONFIRM_PAPER

    st.sidebar.header("Trading Profile")
    if environment == "live":
        st.sidebar.error(f"ENV: {environment}")
    else:
        st.sidebar.success(f"ENV: {environment}")
    st.sidebar.text(f"Profile ID: {profile.get('profile_id', settings.profile_id)}")
    st.sidebar.text(f"API: {settings.api_base_url}")

    if "positions" not in st.session_state:
        try:
            st.session_state["positions"] = _fetch_positions(settings.api_base_url, settings.profile_id)
            st.session_state["positions_last_refresh"] = datetime.now(UTC)
        except ApiError as exc:
            st.error(str(exc))
            st.stop()

    if st.button("Refresh positions"):
        try:
            st.session_state["positions"] = _fetch_positions(settings.api_base_url, settings.profile_id)
            st.session_state["positions_last_refresh"] = datetime.now(UTC)
        except ApiError as exc:
            st.error(str(exc))
            st.stop()

    last_refresh = st.session_state.get("positions_last_refresh")
    if last_refresh:
        st.caption(f"Last refresh: {last_refresh.isoformat()}")

    df = _positions_to_frame(st.session_state["positions"])
    _render_positions(df)

    st.divider()
    _render_kill_switch(settings.api_base_url, settings.profile_id, confirm_phrase)


if __name__ == "__main__":
    main()
