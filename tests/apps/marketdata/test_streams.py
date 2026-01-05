from __future__ import annotations

import asyncio
from types import SimpleNamespace

from apps.marketdata.streams import apply_symbol_limit, normalize_symbols, resolve_feed, run_marketdata_stream


class FakeCache:
    def __init__(self, events: list[str]) -> None:
        self.events = events

    async def set_watchlist(self, _profile_id: str, _symbols: list[str]) -> None:
        self.events.append("watchlist")

    async def store_quote(self, _profile_id: str, _quote: object) -> None:
        self.events.append("quote")

    async def store_trade(self, _profile_id: str, _trade: object) -> None:
        self.events.append("trade")

    async def append_bar(self, _profile_id: str, _bar: object, *, max_bars: int) -> None:
        _ = max_bars
        self.events.append("bar")

    async def close(self) -> None:
        return None


class FakeStream:
    def __init__(self) -> None:
        self.quote_handler = None
        self.trade_handler = None
        self.bar_handler = None

    def subscribe_quotes(self, handler, *_symbols: str) -> None:
        self.quote_handler = handler

    def subscribe_trades(self, handler, *_symbols: str) -> None:
        self.trade_handler = handler

    def subscribe_bars(self, handler, *_symbols: str) -> None:
        self.bar_handler = handler

    def run(self) -> None:
        if self.quote_handler:
            asyncio.run(self.quote_handler({"symbol": "AAPL"}))
        if self.trade_handler:
            asyncio.run(self.trade_handler({"symbol": "AAPL"}))
        if self.bar_handler:
            asyncio.run(self.bar_handler({"symbol": "AAPL"}))


def _build_settings() -> SimpleNamespace:
    return SimpleNamespace(
        marketdata_stream_enabled=True,
        marketdata_symbols=["AAPL"],
        marketdata_max_symbols=30,
        marketdata_ws_max_backoff_seconds=1,
        marketdata_subscribe_quotes=True,
        marketdata_subscribe_trades=True,
        marketdata_subscribe_bars=True,
        marketdata_bar_timeframe="1Min",
        marketdata_bars_max=5,
        engine_profile_id="paper",
        data_feed="iex",
        redis_url="redis://local",
        marketdata_cache_namespace="test",
        marketdata_cache_ttl_seconds=5,
        marketdata_ws_url="",
        api_key="key",
        api_secret="secret",
    )


def test_normalize_symbols_dedupes_and_uppercases() -> None:
    symbols = normalize_symbols([" aapl ", "MSFT", "aapl", "", "Nvda"])
    assert symbols == ["AAPL", "MSFT", "NVDA"]


def test_apply_symbol_limit_trims() -> None:
    symbols = apply_symbol_limit(["AAPL", "MSFT", "NVDA"], 2)
    assert symbols == ["AAPL", "MSFT"]


def test_resolve_feed_defaults_to_iex() -> None:
    settings = SimpleNamespace(data_feed="unknown")
    feed = resolve_feed(settings)
    assert feed.value == "iex"


def test_run_marketdata_stream_writes_cache_once() -> None:
    events: list[str] = []

    cache_instances: list[FakeCache] = []

    def cache_factory(_settings) -> FakeCache:
        cache = FakeCache(events)
        cache_instances.append(cache)
        return cache

    def stream_factory(_settings) -> FakeStream:
        return FakeStream()

    settings = _build_settings()

    run_marketdata_stream(
        settings,
        stream_factory=stream_factory,
        cache_factory=cache_factory,
        sleep_fn=lambda _seconds: None,
        max_cycles=1,
    )

    assert events == ["watchlist", "quote", "trade", "bar"]
    assert len(cache_instances) == 2
