"""I/O helpers for persisting ARK ETF holding snapshots."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Mapping

import pandas as pd

from .domain import Holding, HoldingSnapshot

logger = logging.getLogger(__name__)


def snapshot_to_dataframe(snapshot: HoldingSnapshot) -> pd.DataFrame:
    """Convert a snapshot into a DataFrame suitable for persistence."""
    rows = [
        {
            "as_of": holding.as_of.isoformat(),
            "etf": holding.etf,
            "company": holding.company,
            "ticker": holding.ticker,
            "cusip": holding.cusip,
            "shares": holding.shares,
            "market_value": holding.market_value,
            "weight": holding.weight,
            "price": holding.price,
        }
        for holding in snapshot.holdings
    ]
    df = pd.DataFrame(rows)
    if df.empty:
        logger.warning("Snapshot for %s on %s contains no holdings.", snapshot.etf, snapshot.as_of)
    return df


def dataframe_to_snapshot(df: pd.DataFrame) -> HoldingSnapshot:
    """Convert a DataFrame created by :func:`snapshot_to_dataframe` back to a snapshot."""
    if df.empty:
        raise ValueError("无法从空的 DataFrame 构建快照")
    required_columns = {"as_of", "etf"}
    missing = required_columns - set(df.columns)
    if missing:
        raise ValueError(f"快照缺少必要列: {', '.join(sorted(missing))}")

    as_of_series = pd.to_datetime(df["as_of"]).dt.date
    as_of = as_of_series.iloc[0]
    etf = str(df["etf"].iloc[0]).strip().upper()

    holdings: list[Holding] = []
    for _, row in df.iterrows():
        holdings.append(
            Holding(
                as_of=as_of,
                etf=etf,
                company=str(row.get("company") or "").strip(),
                ticker=str(row.get("ticker") or "").strip().upper(),
                cusip=str(row.get("cusip") or "").strip() or None,
                shares=_maybe_float(row.get("shares")),
                market_value=_maybe_float(row.get("market_value")),
                weight=_maybe_float(row.get("weight")),
                price=_maybe_float(row.get("price")),
            )
        )

    return HoldingSnapshot(etf=etf, as_of=as_of, holdings=holdings)


def load_snapshot_csv(path: str | Path) -> HoldingSnapshot:
    """Load a snapshot stored as CSV."""
    csv_path = Path(path)
    logger.debug("Loading snapshot csv: %s", csv_path)
    df = pd.read_csv(csv_path)
    return dataframe_to_snapshot(df)


def write_snapshot_csv(snapshot: HoldingSnapshot, path: str | Path) -> None:
    """Persist a snapshot to CSV."""
    csv_path = Path(path)
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    df = snapshot_to_dataframe(snapshot)
    df.to_csv(csv_path, index=False)
    logger.debug("Wrote snapshot csv: %s (rows=%d)", csv_path, len(df))


def snapshot_collection_to_folder(snapshots: Mapping[str, HoldingSnapshot], folder: str | Path) -> None:
    """Persist a mapping of ETF -> snapshot into a folder of CSV files."""
    target = Path(folder)
    target.mkdir(parents=True, exist_ok=True)
    for etf, snapshot in snapshots.items():
        write_snapshot_csv(snapshot, target / f"{etf}.csv")


def load_snapshot_folder(folder: str | Path) -> dict[str, HoldingSnapshot]:
    """Load all CSV snapshots within a folder into a dict keyed by ETF."""
    source = Path(folder)
    if not source.exists():
        return {}
    snapshots: dict[str, HoldingSnapshot] = {}
    for path in sorted(source.glob("*.csv")):
        try:
            snapshot = load_snapshot_csv(path)
        except Exception as exc:  # pragma: no cover - defensive log
            logger.error("无法加载快照 %s: %s", path, exc)
            continue
        snapshots[snapshot.etf] = snapshot
    return snapshots


def _maybe_float(value: object) -> float | None:
    if value is None:
        return None
    if isinstance(value, float):
        return value
    if isinstance(value, int):
        return float(value)
    if isinstance(value, str) and not value.strip():
        return None
    try:
        return float(value)
    except Exception:
        return None
