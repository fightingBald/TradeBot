"""Provider utilities to fetch ARK ETF holdings."""

from __future__ import annotations

import io
import logging

import pandas as pd
import requests

from .domain import Holding, HoldingSnapshot
from .transform import parse_snapshot

logger = logging.getLogger(__name__)

FUND_CSV: dict[str, str] = {
    "ARKK": "https://assets.ark-funds.com/fund-documents/funds-etf-csv/ARK_INNOVATION_ETF_ARKK_HOLDINGS.csv",
    "ARKQ": "https://assets.ark-funds.com/fund-documents/funds-etf-csv/ARK_AUTONOMOUS_TECH._%26_ROBOTICS_ETF_ARKQ_HOLDINGS.csv",
    "ARKG": "https://assets.ark-funds.com/fund-documents/funds-etf-csv/ARK_GENOMIC_REVOLUTION_ETF_ARKG_HOLDINGS.csv",
    "ARKF": "https://assets.ark-funds.com/fund-documents/funds-etf-csv/ARK_FINTECH_INNOVATION_ETF_ARKF_HOLDINGS.csv",
    "ARKW": "https://assets.ark-funds.com/fund-documents/funds-etf-csv/ARK_NEXT_GENERATION_INTERNET_ETF_ARKW_HOLDINGS.csv",
    "ARKX": "https://assets.ark-funds.com/fund-documents/funds-etf-csv/ARK_SPACE_EXPLORATION_%26_INNOVATION_ETF_ARKX_HOLDINGS.csv",
}

USER_AGENT = "ark-holdings/1.0 (+https://github.com/huayitang)"


def fetch_holdings_csv(url: str, *, timeout: int = 30) -> pd.DataFrame:
    """Fetch holdings CSV and return as DataFrame."""
    logger.debug("Fetching ARK holdings CSV: %s", url)
    response = requests.get(url, timeout=timeout, headers={"User-Agent": USER_AGENT})
    response.raise_for_status()
    return pd.read_csv(io.StringIO(response.text))


def fetch_holdings_snapshot(etf: str, *, timeout: int = 30) -> HoldingSnapshot:
    """Fetch holdings snapshot for specific ETF symbol."""
    etf_upper = etf.upper()
    if etf_upper not in FUND_CSV:
        raise ValueError(f"Unsupported ETF symbol: {etf}")
    df_raw = fetch_holdings_csv(FUND_CSV[etf_upper], timeout=timeout)
    if df_raw.empty:
        raise ValueError(f"CSV 返回空数据：{etf_upper}")
    as_of_ts, df_clean = parse_snapshot(df_raw)
    as_of_date = as_of_ts.date()
    holdings = []
    for _, row in df_clean.iterrows():
        holding = Holding(
            as_of=as_of_date,
            etf=etf_upper,
            company=str(row.get("company") or row.get("name") or "").strip(),
            ticker=str(row.get("ticker") or "").strip().upper(),
            cusip=str(row.get("cusip") or "").strip() or None,
            shares=row.get("shares"),
            market_value=row.get("market_value"),
            weight=row.get("weight"),
            price=row.get("price"),
        )
        holdings.append(holding)
    logger.info("Fetched %d holdings for %s as of %s", len(holdings), etf_upper, as_of_date)
    return HoldingSnapshot(etf=etf_upper, as_of=as_of_date, holdings=holdings)


def fetch_all_snapshots(*, timeout: int = 30) -> dict[str, HoldingSnapshot]:
    """Fetch snapshots for all supported ETFs."""
    snapshots: dict[str, HoldingSnapshot] = {}
    for etf in FUND_CSV:
        try:
            snapshots[etf] = fetch_holdings_snapshot(etf, timeout=timeout)
        except Exception as exc:  # pragma: no cover - network issues
            logger.error("Failed to fetch %s holdings: %s", etf, exc)
    return snapshots
