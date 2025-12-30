from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncIterator

from redis.asyncio import Redis

from core.domain.commands import Command

logger = logging.getLogger(__name__)


class RedisCommandBus:
    def __init__(self, redis_url: str, queue_name: str) -> None:
        self._client = Redis.from_url(redis_url, decode_responses=True)
        self._queue_name = queue_name

    async def publish(self, command: Command) -> None:
        await self._client.lpush(self._queue_name, command.model_dump_json())
        logger.info("Published command %s type=%s", command.command_id, command.type)

    async def consume(self) -> AsyncIterator[Command]:
        while True:
            try:
                result = await self._client.brpop(self._queue_name, timeout=1)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Command bus read failed")
                await asyncio.sleep(1)
                continue

            if not result:
                continue

            _, payload = result
            try:
                command = Command.model_validate_json(payload)
            except Exception:
                logger.exception("Failed to decode command payload: %s", payload)
                continue
            yield command

    async def close(self) -> None:
        await self._client.close()
