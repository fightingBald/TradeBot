"""Fetch ARK ETF holdings snapshots and store as CSV."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from data_sources.ark_holdings import FUND_CSV, fetch_holdings_snapshot


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch ARK ETF holdings snapshots.")
    parser.add_argument(
        "--etfs",
        help="Comma separated ETF symbols (default: all).",
    )
    parser.add_argument(
        "--output-dir",
        default="data/ark_holdings",
        help="Directory to store CSV snapshots (default: data/ark_holdings).",
    )
    parser.add_argument("--timeout", type=int, default=30, help="HTTP timeout seconds.")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.etfs:
        symbols = [token.strip().upper() for token in args.etfs.split(",") if token.strip()]
    else:
        symbols = list(FUND_CSV.keys())

    for etf in symbols:
        snapshot = fetch_holdings_snapshot(etf, timeout=args.timeout)
        filename = output_dir / f"{snapshot.etf}_{snapshot.as_of.isoformat()}.csv"
        if filename.exists():
            print(f"[skip] {filename} already exists")
            continue
        df = snapshot_to_dataframe(snapshot)
        df.to_csv(filename, index=False)
        print(f"[ok] {filename}")


def snapshot_to_dataframe(snapshot):
    import pandas as pd

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
    return pd.DataFrame(rows)


if __name__ == "__main__":
    main()
