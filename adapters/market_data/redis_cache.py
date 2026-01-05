from __future__ import annotations

import json
import logging
from collections.abc import Iterable, Sequence

from redis.asyncio import Redis

from core.domain.market_data import BarSnapshot, QuoteSnapshot, TradeSnapshot
from core.ports.market_data_cache import MarketDataCache

logger = logging.getLogger(__name__)


class RedisMarketDataCache(MarketDataCache):
    """Redis-backed cache for live market data snapshots."""

    def __init__(
        self,
        redis_url: str,
        *,
        namespace: str = "marketdata",
        ttl_seconds: int | None = 30,
        client: Redis | None = None,
    ) -> None:
        self._client = client or Redis.from_url(redis_url, decode_responses=True)
        self._namespace = namespace
        self._ttl_seconds = ttl_seconds

    def _key(self, profile_id: str, kind: str, symbol: str | None = None, *, timeframe: str | None = None) -> str:
        parts = [self._namespace, profile_id, kind]
        if timeframe:
            parts.append(timeframe)
        if symbol:
            parts.append(symbol.upper())
        return ":".join(parts)

    def _watchlist_key(self, profile_id: str) -> str:
        return self._key(profile_id, "watchlist")

    def _quote_key(self, profile_id: str, symbol: str) -> str:
        return self._key(profile_id, "quote", symbol)

    def _trade_key(self, profile_id: str, symbol: str) -> str:
        return self._key(profile_id, "trade", symbol)

    def _bar_key(self, profile_id: str, symbol: str, timeframe: str) -> str:
        return self._key(profile_id, "bars", symbol, timeframe=timeframe)

    async def store_quote(self, profile_id: str, quote: QuoteSnapshot) -> None:
        payload = quote.model_dump_json()
        if self._ttl_seconds:
            await self._client.set(self._quote_key(profile_id, quote.symbol), payload, ex=self._ttl_seconds)
        else:
            await self._client.set(self._quote_key(profile_id, quote.symbol), payload)

    async def store_trade(self, profile_id: str, trade: TradeSnapshot) -> None:
        payload = trade.model_dump_json()
        if self._ttl_seconds:
            await self._client.set(self._trade_key(profile_id, trade.symbol), payload, ex=self._ttl_seconds)
        else:
            await self._client.set(self._trade_key(profile_id, trade.symbol), payload)

    async def append_bar(self, profile_id: str, bar: BarSnapshot, *, max_bars: int) -> None:
        if max_bars <= 0:
            logger.warning("Skip bar append because max_bars <= 0")
            return
        key = self._bar_key(profile_id, bar.symbol, bar.timeframe)
        payload = bar.model_dump_json()
        await self._client.rpush(key, payload)
        await self._client.ltrim(key, -max_bars, -1)

    async def set_watchlist(self, profile_id: str, symbols: Sequence[str]) -> None:
        normalized = []
        seen = set()
        for symbol in symbols:
            item = symbol.strip().upper()
            if not item or item in seen:
                continue
            seen.add(item)
            normalized.append(item)
        payload = json.dumps(normalized, ensure_ascii=True)
        await self._client.set(self._watchlist_key(profile_id), payload)

    async def get_watchlist(self, profile_id: str) -> list[str]:
        payload = await self._client.get(self._watchlist_key(profile_id))
        if not payload:
            return []
        try:
            data = json.loads(payload)
        except json.JSONDecodeError:
            logger.warning("Failed to decode watchlist payload")
            return []
        return [str(item).upper() for item in data if str(item).strip()]

    async def get_latest_quotes(self, profile_id: str, symbols: Iterable[str]) -> dict[str, QuoteSnapshot]:
        symbol_list = [symbol.strip().upper() for symbol in symbols if symbol and symbol.strip()]
        if not symbol_list:
            return {}
        keys = [self._quote_key(profile_id, symbol) for symbol in symbol_list]
        payloads = await self._client.mget(keys)
        results: dict[str, QuoteSnapshot] = {}
        for symbol, payload in zip(symbol_list, payloads, strict=False):
            if not payload:
                continue
            try:
                results[symbol] = QuoteSnapshot.model_validate_json(payload)
            except Exception:
                logger.exception("Failed to decode quote payload")
        return results

    async def get_latest_trades(self, profile_id: str, symbols: Iterable[str]) -> dict[str, TradeSnapshot]:
        symbol_list = [symbol.strip().upper() for symbol in symbols if symbol and symbol.strip()]
        if not symbol_list:
            return {}
        keys = [self._trade_key(profile_id, symbol) for symbol in symbol_list]
        payloads = await self._client.mget(keys)
        results: dict[str, TradeSnapshot] = {}
        for symbol, payload in zip(symbol_list, payloads, strict=False):
            if not payload:
                continue
            try:
                results[symbol] = TradeSnapshot.model_validate_json(payload)
            except Exception:
                logger.exception("Failed to decode trade payload")
        return results

    async def get_recent_bars(
        self, profile_id: str, symbols: Iterable[str], *, limit: int, timeframe: str = "1Min"
    ) -> dict[str, list[BarSnapshot]]:
        if limit <= 0:
            return {}
        results: dict[str, list[BarSnapshot]] = {}
        for symbol in symbols:
            item = symbol.strip().upper()
            if not item:
                continue
            key = self._bar_key(profile_id, item, timeframe)
            payloads = await self._client.lrange(key, -limit, -1)
            if not payloads:
                continue
            bars: list[BarSnapshot] = []
            for payload in payloads:
                try:
                    bars.append(BarSnapshot.model_validate_json(payload))
                except Exception:
                    logger.exception("Failed to decode bar payload")
            if bars:
                results[item] = bars
        return results

    async def close(self) -> None:
        await self._client.close()
