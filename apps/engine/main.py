from __future__ import annotations

import asyncio
import logging
from typing import Any

from adapters.brokers.alpaca import AlpacaBrokerAdapter
from adapters.messaging.redis_command_bus import RedisCommandBus
from adapters.storage.sqlite_store import SqliteStateStore
from core.domain.commands import Command, CommandType
from core.settings import Settings

logger = logging.getLogger(__name__)


def _configure_logging() -> None:
    root_logger = logging.getLogger()
    if root_logger.handlers:
        return
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


def _run_trading_stream(settings: Settings) -> None:
    try:
        from alpaca.trading.stream import TradingStream
    except Exception:
        logger.exception("Failed to import Alpaca trading stream")
        return

    stream = TradingStream(settings.api_key, settings.api_secret, paper=settings.paper_trading)

    async def on_trade_update(data: Any) -> None:
        event = getattr(data, "event", None)
        logger.info("Trade update event=%s", event)

    stream.subscribe_trade_updates(on_trade_update)
    try:
        stream.run()
    except Exception:
        logger.exception("Trading stream stopped unexpectedly")


async def _sync_positions_loop(
    broker: AlpacaBrokerAdapter,
    store: SqliteStateStore,
    profile_id: str,
    interval_seconds: int,
) -> None:
    while True:
        try:
            positions = await asyncio.to_thread(broker.get_positions)
            await asyncio.to_thread(store.upsert_positions, profile_id, positions)
        except Exception:
            logger.exception("Position sync failed")
        await asyncio.sleep(interval_seconds)


async def _handle_command(
    command: Command,
    broker: AlpacaBrokerAdapter,
    store: SqliteStateStore,
    profile_id: str,
) -> None:
    if command.profile_id != profile_id:
        logger.info("Ignoring command %s for profile %s", command.command_id, command.profile_id)
        return

    if command.type == CommandType.KILL_SWITCH:
        logger.warning("Executing kill switch command_id=%s", command.command_id)
        await asyncio.to_thread(broker.close_all_positions, True)
        await asyncio.to_thread(store.upsert_positions, profile_id, [])
        return

    logger.info("Received command %s type=%s (not implemented)", command.command_id, command.type)


async def _command_loop(
    bus: RedisCommandBus,
    broker: AlpacaBrokerAdapter,
    store: SqliteStateStore,
    profile_id: str,
) -> None:
    async for command in bus.consume():
        try:
            await _handle_command(command, broker, store, profile_id)
        except Exception:
            logger.exception("Command handling failed")


async def run_engine() -> None:
    settings = Settings()
    logger.info(
        "Engine starting profile=%s poll=%ss ws=%s",
        settings.engine_profile_id,
        settings.engine_poll_interval_seconds,
        settings.engine_enable_trading_ws,
    )
    broker = AlpacaBrokerAdapter(settings)
    store = SqliteStateStore(settings.database_url)
    bus = RedisCommandBus(settings.redis_url, settings.command_queue_name)

    tasks = [
        asyncio.create_task(
            _sync_positions_loop(
                broker,
                store,
                settings.engine_profile_id,
                settings.engine_poll_interval_seconds,
            )
        ),
        asyncio.create_task(_command_loop(bus, broker, store, settings.engine_profile_id)),
    ]

    if settings.engine_enable_trading_ws:
        tasks.append(asyncio.create_task(asyncio.to_thread(_run_trading_stream, settings)))
    else:
        logger.info("Trading WS disabled")

    try:
        await asyncio.gather(*tasks)
    finally:
        await bus.close()
        store.close()


def main() -> None:
    _configure_logging()
    asyncio.run(run_engine())


if __name__ == "__main__":
    main()
