from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from core.domain.order import Fill, Order
from core.domain.position import Position


class StateStore(Protocol):
    """Persistence interface for trading state snapshots."""

    def upsert_positions(self, profile_id: str, positions: Sequence[Position]) -> None:
        """Persist the latest positions snapshot."""

    def list_positions(self, profile_id: str) -> list[Position]:
        """Load the latest positions snapshot."""

    def upsert_order(self, profile_id: str, order: Order, *, source: str | None = None) -> None:
        """Persist or update an order record."""

    def list_orders(self, profile_id: str, *, limit: int = 100) -> list[Order]:
        """Load recent orders."""

    def record_fill(self, profile_id: str, fill: Fill) -> None:
        """Persist a fill record."""

    def list_fills(self, profile_id: str, *, limit: int = 100) -> list[Fill]:
        """Load recent fills."""

    def has_protection_link(self, profile_id: str, entry_order_id: str) -> bool:
        """Return True if entry order already has a protection link."""

    def create_protection_link(self, profile_id: str, entry_order_id: str, protection_order_id: str) -> None:
        """Persist a trailing stop protection link."""
