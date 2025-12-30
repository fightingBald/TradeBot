from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Protocol

from core.domain.commands import Command


class CommandBus(Protocol):
    """Message bus for trading commands."""

    async def publish(self, command: Command) -> None:
        """Publish a command to the bus."""

    async def consume(self) -> AsyncIterator[Command]:
        """Yield commands from the bus."""

    async def close(self) -> None:
        """Close any underlying connections."""
