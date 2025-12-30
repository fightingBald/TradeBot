from __future__ import annotations

import asyncio

import pytest

from adapters.messaging.redis_command_bus import RedisCommandBus
from core.domain.commands import Command, CommandType


class FakeRedis:
    def __init__(self) -> None:
        self.items: list[str] = []
        self.closed = False

    async def lpush(self, _name: str, value: str) -> None:
        self.items.insert(0, value)

    async def brpop(self, name: str, timeout: int = 1):
        if not self.items:
            await asyncio.sleep(0)
            return None
        return name, self.items.pop()

    async def close(self) -> None:
        self.closed = True


def test_publish_and_consume(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _run() -> None:
        fake = FakeRedis()
        monkeypatch.setattr("adapters.messaging.redis_command_bus.Redis.from_url", lambda *_a, **_k: fake)

        bus = RedisCommandBus("redis://localhost:6379/0", "alpaca:commands")
        command = Command(type=CommandType.KILL_SWITCH, profile_id="default", payload={"reason": "test"})

        await bus.publish(command)

        stream = bus.consume()
        received = await asyncio.wait_for(anext(stream), timeout=1)
        await stream.aclose()
        await bus.close()

        assert received.command_id == command.command_id
        assert received.type is CommandType.KILL_SWITCH
        assert fake.closed is True

    asyncio.run(_run())
