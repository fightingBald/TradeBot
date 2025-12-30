from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from adapters.brokers.alpaca_service import AlpacaBrokerService
from core.domain.position import Position
from core.ports.broker import BrokerPort
from core.ports.market_data import MarketDataPort
from core.settings import Settings


class AlpacaBrokerAdapter(BrokerPort, MarketDataPort):
    """Expose Alpaca service through core ports."""

    def __init__(self, settings: Settings) -> None:
        self._service = AlpacaBrokerService(settings)

    def get_positions(self) -> Sequence[Position]:
        return self._service.get_positions()

    def get_latest_quotes(self, symbols: Iterable[str]) -> dict[str, Mapping[str, Any]]:
        return self._service.get_latest_quotes(symbols)

    def cancel_open_orders(self) -> list[Any] | Mapping[str, Any]:
        return self._service.cancel_open_orders()

    def close_all_positions(self, cancel_orders: bool | None = True) -> list[Any] | Mapping[str, Any]:
        return self._service.close_all_positions(cancel_orders=cancel_orders)
