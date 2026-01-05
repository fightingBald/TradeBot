from __future__ import annotations

import asyncio

from adapters.market_data.redis_cache import RedisMarketDataCache
from core.domain.market_data import BarSnapshot, QuoteSnapshot, TradeSnapshot


class FakeRedis:
    def __init__(self) -> None:
        self.store: dict[str, str] = {}
        self.lists: dict[str, list[str]] = {}

    async def set(self, key: str, value: str, ex: int | None = None) -> None:
        _ = ex
        self.store[key] = value

    async def get(self, key: str) -> str | None:
        return self.store.get(key)

    async def mget(self, keys: list[str]) -> list[str | None]:
        return [self.store.get(key) for key in keys]

    async def rpush(self, key: str, value: str) -> None:
        self.lists.setdefault(key, []).append(value)

    async def ltrim(self, key: str, start: int, end: int) -> None:
        values = self.lists.get(key, [])
        size = len(values)
        if start < 0:
            start = max(size + start, 0)
        if end < 0:
            end = size + end
        self.lists[key] = values[start : end + 1]

    async def lrange(self, key: str, start: int, end: int) -> list[str]:
        values = self.lists.get(key, [])
        size = len(values)
        if start < 0:
            start = max(size + start, 0)
        if end < 0:
            end = size + end
        return values[start : end + 1]

    async def close(self) -> None:
        return None


def _build_cache() -> RedisMarketDataCache:
    fake = FakeRedis()
    return RedisMarketDataCache("redis://local", namespace="test", ttl_seconds=None, client=fake)


def test_store_and_get_quotes_and_trades() -> None:
    cache = _build_cache()
    quote = QuoteSnapshot(symbol="AAPL", bid_price="100", ask_price="101")
    trade = TradeSnapshot(symbol="AAPL", price="100.5", size="10")

    asyncio.run(cache.store_quote("paper", quote))
    asyncio.run(cache.store_trade("paper", trade))

    quotes = asyncio.run(cache.get_latest_quotes("paper", ["AAPL"]))
    trades = asyncio.run(cache.get_latest_trades("paper", ["AAPL"]))

    assert quotes["AAPL"].ask_price == quote.ask_price
    assert trades["AAPL"].price == trade.price


def test_append_bars_trims_to_max() -> None:
    cache = _build_cache()
    bars = [
        BarSnapshot(symbol="AAPL", timeframe="1Min", open="1", high="2", low="0.5", close="1.5"),
        BarSnapshot(symbol="AAPL", timeframe="1Min", open="1.5", high="2.5", low="1", close="2"),
        BarSnapshot(symbol="AAPL", timeframe="1Min", open="2", high="3", low="1.5", close="2.5"),
    ]

    for bar in bars:
        asyncio.run(cache.append_bar("paper", bar, max_bars=2))

    recent = asyncio.run(cache.get_recent_bars("paper", ["AAPL"], limit=10, timeframe="1Min"))
    assert len(recent["AAPL"]) == 2
    assert recent["AAPL"][0].open == bars[1].open


def test_watchlist_round_trip() -> None:
    cache = _build_cache()
    asyncio.run(cache.set_watchlist("paper", ["aapl", "MSFT", "aapl"]))
    watchlist = asyncio.run(cache.get_watchlist("paper"))
    assert watchlist == ["AAPL", "MSFT"]
