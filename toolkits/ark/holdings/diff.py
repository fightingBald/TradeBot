"""Diff utilities to compare ARK ETF holding snapshots."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List

from .domain import Holding, HoldingSnapshot


@dataclass
class HoldingChange:
    etf: str
    ticker: str
    company: str
    action: str  # "buy" | "sell" | "new" | "exit"
    shares_change: float
    weight_change: float
    market_value_change: float | None
    previous: Holding | None
    current: Holding | None


def _build_index(snapshot: HoldingSnapshot) -> Dict[str, Holding]:
    return {holding.ticker.upper(): holding for holding in snapshot.holdings}


def diff_snapshots(
    previous: HoldingSnapshot,
    current: HoldingSnapshot,
    *,
    weight_threshold: float = 1e-4,
    share_threshold: float = 1.0,
) -> List[HoldingChange]:
    """Compare two snapshots and return holding changes.

    Args:
        previous: Baseline snapshot.
        current: Latest snapshot.
        weight_threshold: Minimum absolute difference in weight to be considered a change.
        share_threshold: Minimum absolute difference in shares to be considered a change.
    """

    if previous.etf != current.etf:
        raise ValueError("Snapshot ETF 不一致，无法比较")

    prev_index = _build_index(previous)
    curr_index = _build_index(current)
    all_tickers = set(prev_index) | set(curr_index)
    changes: List[HoldingChange] = []

    for ticker in sorted(all_tickers):
        prev = prev_index.get(ticker)
        curr = curr_index.get(ticker)

        if prev is None and curr is not None:
            changes.append(
                HoldingChange(
                    etf=current.etf,
                    ticker=curr.ticker,
                    company=curr.company,
                    action="new",
                    shares_change=curr.shares or 0.0,
                    weight_change=curr.weight or 0.0,
                    market_value_change=curr.market_value,
                    previous=None,
                    current=curr,
                )
            )
            continue

        if prev is not None and curr is None:
            changes.append(
                HoldingChange(
                    etf=previous.etf,
                    ticker=prev.ticker,
                    company=prev.company,
                    action="exit",
                    shares_change=-(prev.shares or 0.0),
                    weight_change=-(prev.weight or 0.0),
                    market_value_change=(
                        -(prev.market_value or 0.0) if prev.market_value else None
                    ),
                    previous=prev,
                    current=None,
                )
            )
            continue

        assert prev is not None and curr is not None
        shares_diff = (curr.shares or 0.0) - (prev.shares or 0.0)
        weight_diff = (curr.weight or 0.0) - (prev.weight or 0.0)
        mv_diff = None
        if curr.market_value is not None and prev.market_value is not None:
            mv_diff = curr.market_value - prev.market_value

        if abs(shares_diff) < share_threshold and abs(weight_diff) < weight_threshold:
            continue

        action = "buy" if shares_diff > 0 else "sell"
        changes.append(
            HoldingChange(
                etf=current.etf,
                ticker=curr.ticker,
                company=curr.company,
                action=action,
                shares_change=shares_diff,
                weight_change=weight_diff,
                market_value_change=mv_diff,
                previous=prev,
                current=curr,
            )
        )

    return changes


def summarize_changes(
    changes: Iterable[HoldingChange], *, top_n: int = 10
) -> Dict[str, List[HoldingChange]]:
    """Split changes into buys and sells sorted by absolute weight change."""

    buys: List[HoldingChange] = []
    sells: List[HoldingChange] = []
    for change in changes:
        if change.action in {"new", "buy"}:
            buys.append(change)
        elif change.action in {"exit", "sell"}:
            sells.append(change)

    buys_sorted = sorted(buys, key=_weight_abs, reverse=True)[:top_n]
    sells_sorted = sorted(sells, key=_weight_abs, reverse=True)[:top_n]
    return {
        "buys": buys_sorted,
        "sells": sells_sorted,
    }


def _weight_abs(change: HoldingChange) -> float:
    return abs(change.weight_change or 0.0)
