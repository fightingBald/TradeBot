from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any, Protocol


class MarketDataPort(Protocol):
    """Market data interface for latest quote access."""

    def get_latest_quotes(self, symbols: Iterable[str]) -> dict[str, Mapping[str, Any]]:
        """Fetch latest quote snapshots."""
