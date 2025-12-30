from __future__ import annotations

import asyncio
import logging
import random
import time
from dataclasses import dataclass
from typing import Any

from adapters.brokers.alpaca import AlpacaBrokerAdapter
from adapters.messaging.redis_command_bus import RedisCommandBus
from adapters.storage.sqlite_store import SqliteStateStore
from core.domain.commands import Command, CommandType
from core.settings import Settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PositionSyncContext:
    broker: AlpacaBrokerAdapter
    store: SqliteStateStore
    profile_id: str
    interval_seconds: int
    min_interval_seconds: int


def _configure_logging() -> None:
    root_logger = logging.getLogger()
    if root_logger.handlers:
        return
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


def _run_trading_stream(
    settings: Settings,
    loop: asyncio.AbstractEventLoop,
    refresh_event: asyncio.Event,
) -> None:
    try:
        from alpaca.trading.stream import TradingStream
    except Exception:
        logger.exception("Failed to import Alpaca trading stream")
        return

    max_backoff = max(1, settings.engine_trading_ws_max_backoff_seconds)
    backoff_seconds = 1

    def _signal_refresh() -> None:
        loop.call_soon_threadsafe(refresh_event.set)

    async def on_trade_update(data: Any) -> None:
        event = getattr(data, "event", None)
        logger.info("Trade update event=%s", event)
        _signal_refresh()

    while True:
        stream = TradingStream(settings.api_key, settings.api_secret, paper=settings.paper_trading)
        stream.subscribe_trade_updates(on_trade_update)
        try:
            logger.info("Trading WS connecting (paper=%s)", settings.paper_trading)
            stream.run()
            logger.warning("Trading WS stopped (reconnecting in %ss)", backoff_seconds)
        except Exception:
            logger.exception("Trading WS stopped unexpectedly (reconnecting in %ss)", backoff_seconds)

        jitter = random.uniform(0, 0.5)
        time.sleep(backoff_seconds + jitter)
        backoff_seconds = min(backoff_seconds * 2, max_backoff)


async def _sync_positions_loop(context: PositionSyncContext, refresh_event: asyncio.Event) -> None:
    last_sync_at = 0.0
    while True:
        triggered_by_event = False
        try:
            try:
                await asyncio.wait_for(refresh_event.wait(), timeout=context.interval_seconds)
                triggered_by_event = True
            except TimeoutError:
                triggered_by_event = False

            if triggered_by_event:
                refresh_event.clear()
            now = time.monotonic()
            elapsed = now - last_sync_at
            if context.min_interval_seconds > 0 and elapsed < context.min_interval_seconds:
                cooldown = context.min_interval_seconds - elapsed
                logger.info("Position sync cooldown %.2fs", cooldown)
                await asyncio.sleep(cooldown)

            reason = "trade_update" if triggered_by_event else "interval"
            logger.info("Syncing positions (reason=%s)", reason)
            positions = await asyncio.to_thread(context.broker.get_positions)
            await asyncio.to_thread(context.store.upsert_positions, context.profile_id, positions)
            last_sync_at = time.monotonic()
        except Exception:
            logger.exception("Position sync failed")
            await asyncio.sleep(1)


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
        "Engine starting profile=%s poll=%ss min_sync=%ss ws=%s ws_backoff_max=%ss",
        settings.engine_profile_id,
        settings.engine_poll_interval_seconds,
        settings.engine_sync_min_interval_seconds,
        settings.engine_enable_trading_ws,
        settings.engine_trading_ws_max_backoff_seconds,
    )
    broker = AlpacaBrokerAdapter(settings)
    store = SqliteStateStore(settings.database_url)
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
