from __future__ import annotations

import logging

import altair as alt
import pandas as pd
import streamlit as st

from apps.ui.api_client import ApiError, request_kill_switch

logger = logging.getLogger(__name__)


def render_positions(df: pd.DataFrame) -> None:
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


def render_kill_switch(api_base_url: str, profile_id: str, confirm_phrase: str) -> str | None:
    st.header("Kill Switch")
    st.warning("This will cancel open orders and close all positions.")
    acknowledge = st.checkbox("I understand this action is irreversible.")

    confirm_input = st.text_input(
        f"Type {confirm_phrase} to confirm",
        type="password" if confirm_phrase == "LIVE" else "default",
    ).strip()
    confirm_ok = confirm_input.upper() == confirm_phrase

    reason = st.text_input("Reason (optional)", placeholder="e.g. risk off")

    if st.button("Execute Kill Switch", disabled=not (acknowledge and confirm_ok)):
        logger.warning("Kill switch requested (profile=%s)", profile_id)
        with st.spinner("Submitting kill switch..."):
            try:
                result = request_kill_switch(
                    api_base_url,
                    profile_id=profile_id,
                    confirm_token=confirm_input,
                    reason=reason,
                )
            except ApiError as exc:
                st.error(f"Kill switch failed: {exc}")
                return None

        st.success(f"Kill switch submitted. Command: {result.get('command_id')}")
        return str(result.get("command_id", ""))

    return None
