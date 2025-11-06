"""Compare ARK holdings snapshots and pretty-print changes."""

from __future__ import annotations

import argparse

from data_sources.ark_holdings import diff_snapshots, summarize_changes
from data_sources.ark_holdings.io import load_snapshot_csv


def main() -> None:
    parser = argparse.ArgumentParser(description="Diff ARK ETF holdings snapshots")
    parser.add_argument(
        "--previous", required=True, help="Path to previous snapshot CSV"
    )
    parser.add_argument("--current", required=True, help="Path to current snapshot CSV")
    parser.add_argument("--top", type=int, default=10, help="Top N changes to display")
    args = parser.parse_args()

    prev_snapshot = load_snapshot_csv(args.previous)
    curr_snapshot = load_snapshot_csv(args.current)

    changes = diff_snapshots(prev_snapshot, curr_snapshot)
    summary = summarize_changes(changes, top_n=args.top)

    if not changes:
        print("No significant changes detected.")
        return

    print_changes("增持 Top", summary["buys"])
    print()
    print_changes("减持 Top", summary["sells"])


def print_changes(title: str, changes):
    print(f"{title}:")
    if not changes:
        print("  无")
        return
    for change in changes:
        shares = change.shares_change or 0.0
        weight_pct = (change.weight_change or 0.0) * 100
        mv = change.market_value_change
        mv_str = f"${mv:,.0f}" if mv is not None else "N/A"
        print(
            f"  {change.ticker:<6} {change.company:<30} {change.action:<4} "
            f"shares: {shares:>12,.0f}  weight: {weight_pct:>6.2f}%  mv: {mv_str}"
        )


if __name__ == "__main__":
    main()
