from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass

from core.ports.broker import BrokerPort
from core.ports.state_store import StateStore

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PositionSyncContext:
    broker: BrokerPort
    store: StateStore
    profile_id: str
    interval_seconds: int
    min_interval_seconds: int


async def sync_positions_loop(context: PositionSyncContext, refresh_event: asyncio.Event) -> None:
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
