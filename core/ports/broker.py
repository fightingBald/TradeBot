from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any, Protocol

from core.domain.order import Order, TrailingStopOrderRequest
from core.domain.position import Position


class BrokerPort(Protocol):
    """Trading broker interface for positions and account actions."""

    def get_positions(self) -> Sequence[Position]:
        """Return current open positions."""

    def cancel_open_orders(self) -> list[Any] | Mapping[str, Any]:
        """Cancel all open orders."""

    def close_all_positions(self, cancel_orders: bool | None = True) -> list[Any] | Mapping[str, Any]:
        """Close all open positions."""

    def submit_trailing_stop_order(self, order: TrailingStopOrderRequest) -> Order:
        """Submit a trailing stop order to the broker."""
