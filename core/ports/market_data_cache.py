from __future__ import annotations

from collections.abc import Iterable, Sequence
from typing import Protocol

from core.domain.market_data import BarSnapshot, QuoteSnapshot, TradeSnapshot


class MarketDataCache(Protocol):
    """Cache interface for live market data snapshots."""

    async def store_quote(self, profile_id: str, quote: QuoteSnapshot) -> None:
        """Persist the latest quote snapshot for a symbol."""

    async def store_trade(self, profile_id: str, trade: TradeSnapshot) -> None:
        """Persist the latest trade snapshot for a symbol."""

    async def append_bar(self, profile_id: str, bar: BarSnapshot, *, max_bars: int) -> None:
        """Append a bar snapshot for a symbol (kept as a capped list)."""

    async def set_watchlist(self, profile_id: str, symbols: Sequence[str]) -> None:
        """Persist the active watchlist symbols."""

    async def get_watchlist(self, profile_id: str) -> list[str]:
        """Return the latest watchlist symbols."""

    async def get_latest_quotes(self, profile_id: str, symbols: Iterable[str]) -> dict[str, QuoteSnapshot]:
        """Fetch cached quotes for the requested symbols."""

    async def get_latest_trades(self, profile_id: str, symbols: Iterable[str]) -> dict[str, TradeSnapshot]:
        """Fetch cached trades for the requested symbols."""

    async def get_recent_bars(
        self, profile_id: str, symbols: Iterable[str], *, limit: int, timeframe: str = "1Min"
    ) -> dict[str, list[BarSnapshot]]:
        """Fetch recent bars for each symbol/timeframe."""

    async def close(self) -> None:
        """Close any underlying resources."""
