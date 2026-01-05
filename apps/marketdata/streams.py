from __future__ import annotations

import asyncio
import logging
import random
import time
from collections.abc import Awaitable, Callable, Iterable

from alpaca.data.enums import DataFeed
from alpaca.data.live import StockDataStream

from adapters.market_data.redis_cache import RedisMarketDataCache
from core.domain.market_data import BarSnapshot, QuoteSnapshot, TradeSnapshot
from core.settings import Settings

logger = logging.getLogger(__name__)


def normalize_symbols(symbols: Iterable[str]) -> list[str]:
    seen = set()
    normalized: list[str] = []
    for symbol in symbols:
        item = symbol.strip().upper()
        if not item or item in seen:
            continue
        seen.add(item)
        normalized.append(item)
    return normalized


def apply_symbol_limit(symbols: list[str], max_symbols: int) -> list[str]:
    if max_symbols <= 0:
        return []
    if len(symbols) <= max_symbols:
        return symbols
    logger.warning("Market data symbols trimmed to max=%s", max_symbols)
    return symbols[:max_symbols]


def resolve_symbols(settings: Settings) -> list[str]:
    return apply_symbol_limit(normalize_symbols(settings.marketdata_symbols), settings.marketdata_max_symbols)


def resolve_feed(settings: Settings) -> DataFeed:
    try:
        return DataFeed(settings.data_feed.lower())
    except ValueError:
        logger.warning("Unknown data feed %s; defaulting to IEX", settings.data_feed)
        return DataFeed.IEX


def build_stream(settings: Settings) -> StockDataStream:
    url_override = settings.marketdata_ws_url or None
    return StockDataStream(
        settings.api_key,
        settings.api_secret,
        raw_data=False,
        feed=resolve_feed(settings),
        url_override=url_override,
    )


def _build_cache(settings: Settings) -> RedisMarketDataCache:
    return RedisMarketDataCache(
        settings.redis_url,
        namespace=settings.marketdata_cache_namespace,
        ttl_seconds=settings.marketdata_cache_ttl_seconds,
    )


def _persist_watchlist(
    settings: Settings,
    symbols: list[str],
    cache_factory: Callable[[Settings], RedisMarketDataCache],
) -> None:
    cache = cache_factory(settings)
    try:
        asyncio.run(cache.set_watchlist(settings.engine_profile_id, symbols))
    finally:
        asyncio.run(cache.close())


def _build_handlers(
    settings: Settings, cache: RedisMarketDataCache
) -> tuple[
    Callable[[object], Awaitable[None]],
    Callable[[object], Awaitable[None]],
    Callable[[object], Awaitable[None]],
]:
    async def on_quote(data: object) -> None:
        try:
            snapshot = QuoteSnapshot.from_alpaca(data)
            await cache.store_quote(settings.engine_profile_id, snapshot)
        except Exception:
            logger.exception("Failed to store quote")

    async def on_trade(data: object) -> None:
        try:
            snapshot = TradeSnapshot.from_alpaca(data)
            await cache.store_trade(settings.engine_profile_id, snapshot)
        except Exception:
            logger.exception("Failed to store trade")

    async def on_bar(data: object) -> None:
        try:
            snapshot = BarSnapshot.from_alpaca(data, timeframe=settings.marketdata_bar_timeframe)
            await cache.append_bar(
                settings.engine_profile_id,
                snapshot,
                max_bars=settings.marketdata_bars_max,
            )
        except Exception:
            logger.exception("Failed to store bar")

    return on_quote, on_trade, on_bar


def _subscribe_stream(
    stream: StockDataStream,
    settings: Settings,
    symbols: list[str],
    handlers: tuple[
        Callable[[object], Awaitable[None]],
        Callable[[object], Awaitable[None]],
        Callable[[object], Awaitable[None]],
    ],
) -> None:
    on_quote, on_trade, on_bar = handlers
    if settings.marketdata_subscribe_quotes:
        stream.subscribe_quotes(on_quote, *symbols)
    if settings.marketdata_subscribe_trades:
        stream.subscribe_trades(on_trade, *symbols)
    if settings.marketdata_subscribe_bars:
        stream.subscribe_bars(on_bar, *symbols)


def _run_stream_cycle(
    settings: Settings,
    symbols: list[str],
    stream_factory: Callable[[Settings], StockDataStream],
    cache_factory: Callable[[Settings], RedisMarketDataCache],
    backoff_seconds: int,
) -> None:
    cache = cache_factory(settings)
    handlers = _build_handlers(settings, cache)
    stream = stream_factory(settings)
    _subscribe_stream(stream, settings, symbols, handlers)

    try:
        logger.info(
            "Market data WS connecting feed=%s symbols=%s",
            settings.data_feed,
            ",".join(symbols),
        )
        stream.run()
        logger.warning("Market data WS stopped (reconnecting in %ss)", backoff_seconds)
    except Exception:
        logger.exception("Market data WS stopped unexpectedly (reconnecting in %ss)", backoff_seconds)
    finally:
        asyncio.run(cache.close())


def run_marketdata_stream(
    settings: Settings,
    *,
    stream_factory: Callable[[Settings], StockDataStream] = build_stream,
    cache_factory: Callable[[Settings], RedisMarketDataCache] = _build_cache,
    sleep_fn: Callable[[float], None] = time.sleep,
    max_cycles: int | None = None,
) -> None:
    if not settings.marketdata_stream_enabled:
        logger.info("Market data stream disabled")
        return

    symbols = resolve_symbols(settings)
    if not symbols:
        logger.warning("No market data symbols configured; MARKETDATA_SYMBOLS is empty")
        return

    _persist_watchlist(settings, symbols, cache_factory)

    max_backoff = max(1, settings.marketdata_ws_max_backoff_seconds)
    backoff_seconds = 1
    cycles = 0

    while True:
        _run_stream_cycle(
            settings,
            symbols,
            stream_factory,
            cache_factory,
            backoff_seconds,
        )

        jitter = random.uniform(0, 0.5)  # noqa: S311
        cycles += 1
        if max_cycles and cycles >= max_cycles:
            break
        sleep_fn(backoff_seconds + jitter)
        backoff_seconds = min(backoff_seconds * 2, max_backoff)
