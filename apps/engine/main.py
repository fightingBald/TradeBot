from __future__ import annotations

import asyncio
import logging

from adapters.brokers.alpaca import AlpacaBrokerAdapter
from adapters.messaging.redis_command_bus import RedisCommandBus
from adapters.storage.sqlalchemy_state_store import SqlAlchemyStateStore
from apps.engine.commands import command_loop as _command_loop, handle_command as _handle_command
from apps.engine.streams import run_trading_stream as _run_trading_stream
from apps.engine.sync import PositionSyncContext, sync_positions_loop as _sync_positions_loop
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


async def run_engine() -> None:
    settings = Settings()
    logger.info(
        "Engine starting profile=%s poll=%ss min_sync=%ss ws=%s ws_backoff_max=%ss",
        settings.engine_profile_id,
        settings.engine_poll_interval_seconds,
        settings.engine_sync_min_interval_seconds,
        settings.engine_enable_trading_ws,
        settings.engine_trading_ws_max_backoff_seconds,
    )
    broker = AlpacaBrokerAdapter(settings)
    store = SqlAlchemyStateStore(settings.database_url)
    bus = RedisCommandBus(settings.redis_url, settings.command_queue_name)

    refresh_event = asyncio.Event()
    loop = asyncio.get_running_loop()

    sync_context = PositionSyncContext(
        broker=broker,
        store=store,
        profile_id=settings.engine_profile_id,
        interval_seconds=settings.engine_poll_interval_seconds,
        min_interval_seconds=settings.engine_sync_min_interval_seconds,
    )

    tasks = [
        asyncio.create_task(_sync_positions_loop(sync_context, refresh_event)),
        asyncio.create_task(_command_loop(bus, broker, store, settings.engine_profile_id)),
    ]

    if settings.engine_enable_trading_ws:
        tasks.append(asyncio.create_task(asyncio.to_thread(_run_trading_stream, settings, loop, refresh_event)))
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


__all__ = [
    "PositionSyncContext",
    "_command_loop",
    "_configure_logging",
    "_handle_command",
    "_run_trading_stream",
    "_sync_positions_loop",
    "main",
    "run_engine",
]
