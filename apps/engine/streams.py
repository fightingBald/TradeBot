from __future__ import annotations

import asyncio
import logging
import random
import time
from typing import Any

from core.settings import Settings

logger = logging.getLogger(__name__)


def run_trading_stream(
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
