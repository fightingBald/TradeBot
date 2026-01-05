from __future__ import annotations

from core.domain.market_data import BarSnapshot, QuoteSnapshot, TradeSnapshot


def test_quote_snapshot_normalizes_symbol() -> None:
    quote = QuoteSnapshot.from_alpaca({"symbol": "aapl", "bid_price": "100", "ask_price": "101"})
    assert quote.symbol == "AAPL"


def test_trade_snapshot_parses_id_and_timestamp() -> None:
    trade = TradeSnapshot.from_alpaca(
        {
            "symbol": "msft",
            "price": "300.5",
            "size": "10",
            "timestamp": "2025-01-01T00:00:00Z",
            "id": "trade-1",
        }
    )
    assert trade.symbol == "MSFT"
    assert trade.trade_id == "trade-1"
    assert trade.timestamp is not None


def test_bar_snapshot_sets_timeframe() -> None:
    bar = BarSnapshot.from_alpaca({"symbol": "tsla", "open": "1"}, timeframe="5Min")
    assert bar.symbol == "TSLA"
    assert bar.timeframe == "5Min"
