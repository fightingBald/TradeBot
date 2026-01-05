from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal

import pandas as pd

from core.domain.market_data import BarSnapshot, QuoteSnapshot, TradeSnapshot
from core.domain.position import Position


def _to_float(value: Decimal | None) -> float:
    if value is None:
        return float("nan")
    return float(value)


def positions_to_frame(positions: Sequence[Position]) -> pd.DataFrame:
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


def market_snapshots_to_frame(
    quotes: dict[str, QuoteSnapshot], trades: dict[str, TradeSnapshot]
) -> pd.DataFrame:
    symbols = sorted(set(quotes.keys()) | set(trades.keys()))
    records: list[dict[str, object]] = []
    for symbol in symbols:
        quote = quotes.get(symbol)
        trade = trades.get(symbol)
        bid_price = _to_float(quote.bid_price) if quote else float("nan")
        ask_price = _to_float(quote.ask_price) if quote else float("nan")
        spread = ask_price - bid_price if quote and quote.bid_price is not None and quote.ask_price is not None else None
        mid = (ask_price + bid_price) / 2 if spread is not None else None
        records.append(
            {
                "symbol": symbol,
                "last_price": _to_float(trade.price) if trade else float("nan"),
                "last_size": _to_float(trade.size) if trade else float("nan"),
                "bid_price": bid_price,
                "ask_price": ask_price,
                "spread": spread,
                "mid": mid,
                "trade_time": trade.timestamp if trade else None,
                "quote_time": quote.timestamp if quote else None,
            }
        )
    return pd.DataFrame.from_records(records)


def bars_to_frame(bars: Sequence[BarSnapshot]) -> pd.DataFrame:
    records: list[dict[str, object]] = []
    for bar in bars:
        records.append(
            {
                "timestamp": bar.timestamp,
                "open": _to_float(bar.open),
                "high": _to_float(bar.high),
                "low": _to_float(bar.low),
                "close": _to_float(bar.close),
                "volume": _to_float(bar.volume),
            }
        )
    df = pd.DataFrame.from_records(records)
    if df.empty:
        return df
    df.sort_values("timestamp", inplace=True)
    return df
