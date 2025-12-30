from __future__ import annotations

import asyncio
import logging

from core.domain.commands import Command, CommandType
from core.ports.broker import BrokerPort
from core.ports.command_bus import CommandBus
from core.ports.state_store import StateStore

logger = logging.getLogger(__name__)


async def handle_command(command: Command, broker: BrokerPort, store: StateStore, profile_id: str) -> None:
    if command.profile_id != profile_id:
        logger.info("Ignoring command %s for profile %s", command.command_id, command.profile_id)
        return

    if command.type == CommandType.KILL_SWITCH:
        logger.warning("Executing kill switch command_id=%s", command.command_id)
        await asyncio.to_thread(broker.close_all_positions, True)
        await asyncio.to_thread(store.upsert_positions, profile_id, [])
        return

    logger.info("Received command %s type=%s (not implemented)", command.command_id, command.type)


async def command_loop(bus: CommandBus, broker: BrokerPort, store: StateStore, profile_id: str) -> None:
    async for command in bus.consume():
        try:
            await handle_command(command, broker, store, profile_id)
        except Exception:
            logger.exception("Command handling failed")
