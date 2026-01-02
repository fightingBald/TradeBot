from __future__ import annotations

import asyncio
import logging
from decimal import Decimal
from uuid import uuid4

from core.domain.commands import Command, CommandType
from core.domain.order import OrderSide, TimeInForce, TrailingStopOrderRequest
from core.ports.broker import BrokerPort
from core.ports.command_bus import CommandBus
from core.ports.state_store import StateStore
from core.settings import Settings

logger = logging.getLogger(__name__)


def _resolve_trailing_qty(
    payload: dict[str, object], store: StateStore, broker: BrokerPort, settings: Settings
) -> Decimal | None:
    qty = payload.get("qty")
    if qty is not None:
        return Decimal(str(qty))

    symbol = str(payload.get("symbol", "")).upper()
    if not symbol:
        return None

    for position in store.list_positions(settings.engine_profile_id):
        if position.symbol.upper() == symbol:
            return position.quantity

    try:
        for position in broker.get_positions():
            if position.symbol.upper() == symbol:
                return position.quantity
    except Exception:
        logger.exception("Failed to refresh positions for trailing stop loss: symbol=%s", symbol)
    return None


def _normalize_trail_percent(raw: object, default_percent: float) -> Decimal:
    if raw is None:
        return Decimal(str(default_percent))
    return Decimal(str(raw))


def _build_trailing_order(
    payload: dict[str, object],
    *,
    side: OrderSide,
    settings: Settings,
    broker: BrokerPort,
    store: StateStore,
) -> TrailingStopOrderRequest | None:
    symbol = str(payload.get("symbol", "")).upper()

    trail_percent = _normalize_trail_percent(payload.get("trail_percent"), settings.engine_trailing_default_percent)
    if not symbol or trail_percent <= 0:
        logger.warning("Trailing stop invalid payload: symbol=%s trail_percent=%s", symbol, trail_percent)
        return None

    if side is OrderSide.BUY:
        raw_qty = payload.get("qty")
        if raw_qty is None:
            logger.warning("Trailing stop buy missing qty: symbol=%s", symbol)
            return None
        qty = Decimal(str(raw_qty))
        try:
            tif = TimeInForce(settings.engine_trailing_buy_tif)
        except ValueError:
            logger.warning("Unsupported trailing buy TIF: %s", settings.engine_trailing_buy_tif)
            return None
    else:
        qty = _resolve_trailing_qty(payload, store, broker, settings)
        if qty is None or qty <= 0:
            logger.warning("Trailing stop loss missing qty: symbol=%s", symbol)
            return None
        try:
            tif = TimeInForce(settings.engine_trailing_sell_tif)
        except ValueError:
            logger.warning("Unsupported trailing sell TIF: %s", settings.engine_trailing_sell_tif)
            return None

    client_order_id = payload.get("client_order_id")
    if not client_order_id:
        client_order_id = f"trail-{side.value}-{uuid4().hex[:12]}"

    return TrailingStopOrderRequest(
        symbol=symbol,
        side=side,
        qty=qty,
        trail_percent=trail_percent,
        time_in_force=tif,
        extended_hours=False,
        client_order_id=str(client_order_id),
    )


async def handle_command(command: Command, broker: BrokerPort, store: StateStore, settings: Settings) -> None:
    profile_id = settings.engine_profile_id
    if command.profile_id != profile_id:
        logger.info("Ignoring command %s for profile %s", command.command_id, command.profile_id)
        return

    if command.type == CommandType.KILL_SWITCH:
        logger.warning("Executing kill switch command_id=%s", command.command_id)
        await asyncio.to_thread(broker.close_all_positions, True)
        await asyncio.to_thread(store.upsert_positions, profile_id, [])
        return

    if command.type in {CommandType.TRAILING_STOP_BUY, CommandType.TRAILING_STOP_SELL}:
        side = OrderSide.BUY if command.type is CommandType.TRAILING_STOP_BUY else OrderSide.SELL
        request = _build_trailing_order(
            command.payload,
            side=side,
            settings=settings,
            broker=broker,
            store=store,
        )
        if request is None:
            return
        order = await asyncio.to_thread(broker.submit_trailing_stop_order, request)
        await asyncio.to_thread(store.upsert_order, profile_id, order, source="ui")
        return

    logger.info("Received command %s type=%s (not implemented)", command.command_id, command.type)


async def command_loop(
    bus: CommandBus,
    broker: BrokerPort,
    store: StateStore,
    settings: Settings,
) -> None:
    async for command in bus.consume():
        try:
            await handle_command(command, broker, store, settings)
        except Exception:
            logger.exception("Command handling failed")
