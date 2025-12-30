from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from core.domain.position import Position


class StateStore(Protocol):
    """Persistence interface for trading state snapshots."""

    def upsert_positions(self, profile_id: str, positions: Sequence[Position]) -> None:
        """Persist the latest positions snapshot."""

    def list_positions(self, profile_id: str) -> list[Position]:
        """Load the latest positions snapshot."""
