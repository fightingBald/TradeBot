from __future__ import annotations

import asyncio
import logging
import random
import time
from datetime import datetime
from decimal import Decimal
from typing import Any

from apps.engine.rules import coerce_tif_for_fractional
from core.domain.order import Fill, Order, OrderSide, TimeInForce, TrailingStopOrderRequest
from core.ports.broker import BrokerPort
from core.ports.state_store import StateStore
from core.settings import Settings

logger = logging.getLogger(__name__)


def _to_mapping(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if hasattr(value, "dict"):
        return value.dict()
    if isinstance(value, dict):
        return value
    if hasattr(value, "__dict__"):
        return dict(value.__dict__)
    return {}


def _parse_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str) and value:
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


def _normalize_enum_text(value: Any) -> str:
    if hasattr(value, "value"):
        return str(value.value).lower()
    text = str(value)
    if "." in text:
        text = text.split(".")[-1]
    return text.lower()


def _order_type(payload: dict[str, Any]) -> str:
    raw = payload.get("order_type") or payload.get("type") or ""
    return _normalize_enum_text(raw)


def _order_side(payload: dict[str, Any]) -> str:
    raw = payload.get("side") or ""
    return _normalize_enum_text(raw)


def _has_bracket(payload: dict[str, Any]) -> bool:
    order_class = str(payload.get("order_class") or "").lower()
    if order_class in {"bracket", "oco", "oto"}:
        return True
    return bool(payload.get("legs") or payload.get("stop_loss") or payload.get("take_profit"))


def _resolve_position_qty(broker: BrokerPort, symbol: str) -> Decimal | None:
    for position in broker.get_positions():
        if position.symbol.upper() == symbol:
            return position.quantity
    return None


def _build_fill_from_order(order_payload: dict[str, Any]) -> Fill | None:
    order_id = order_payload.get("id") or order_payload.get("order_id")
    symbol = order_payload.get("symbol")
    side = _normalize_enum_text(order_payload.get("side") or "")
    qty = order_payload.get("filled_qty") or order_payload.get("filled_quantity") or order_payload.get("qty")
    price = order_payload.get("filled_avg_price") or order_payload.get("avg_fill_price")
    filled_at = (
        order_payload.get("filled_at")
        or order_payload.get("updated_at")
        or order_payload.get("timestamp")
        or None
    )
    if not order_id or not symbol or not side or qty is None:
        return None
    return Fill(
        order_id=str(order_id),
        symbol=str(symbol),
        side=side,
        qty=Decimal(str(qty)),
        price=Decimal(str(price)) if price is not None else None,
        filled_at=_parse_datetime(filled_at),
    )


def _auto_protect_on_fill(
    *,
    order_payload: dict[str, Any],
    settings: Settings,
    broker: BrokerPort,
    store: StateStore,
) -> None:
    if not settings.engine_auto_protect_enabled:
        return

    order_id, symbol, skip_reason = _auto_protect_context(order_payload, settings, store)
    if skip_reason:
        logger.info("Auto-protect skipped: %s order_id=%s", skip_reason, order_id)
        return
    if not order_id or not symbol:
        return

    qty = _resolve_position_qty(broker, symbol)
    if qty is None or qty <= 0:
        logger.warning("Auto-protect skipped: no position for symbol=%s", symbol)
        return

    try:
        tif = TimeInForce(settings.engine_trailing_sell_tif)
    except ValueError:
        logger.warning("Auto-protect unsupported sell TIF: %s", settings.engine_trailing_sell_tif)
        return
    tif = coerce_tif_for_fractional(qty, tif, context="auto_protect")

    client_order_id = f"auto-protect-{str(order_id)[:20]}"
    request = TrailingStopOrderRequest(
        symbol=symbol,
        side=OrderSide.SELL,
        qty=qty,
        trail_percent=Decimal(str(settings.engine_trailing_default_percent)),
        time_in_force=tif,
        extended_hours=False,
        client_order_id=client_order_id,
    )

    try:
        protection_order = broker.submit_trailing_stop_order(request)
    except Exception:
        logger.exception("Auto-protect failed: order_id=%s symbol=%s", order_id, symbol)
        return

    store.upsert_order(settings.engine_profile_id, protection_order, source="auto_protect")
    store.create_protection_link(settings.engine_profile_id, str(order_id), protection_order.order_id)
    logger.info("Auto-protect created order_id=%s", protection_order.order_id)


def _auto_protect_context(
    order_payload: dict[str, Any],
    settings: Settings,
    store: StateStore,
) -> tuple[str | None, str | None, str | None]:
    order_id = order_payload.get("id") or order_payload.get("order_id")
    symbol = str(order_payload.get("symbol") or "").upper()
    if not order_id or not symbol:
        return None, None, "missing_order_fields"

    order_type = _order_type(order_payload)
    if _order_side(order_payload) != "buy":
        return str(order_id), symbol, "non_buy_order"
    if order_type not in set(settings.engine_auto_protect_order_types):
        return str(order_id), symbol, f"order_type={order_type}"
    if _has_bracket(order_payload):
        return str(order_id), symbol, "bracket_or_legs"
    if store.has_protection_link(settings.engine_profile_id, str(order_id)):
        return str(order_id), symbol, "already_linked"
    return str(order_id), symbol, None


def process_trade_update(
    data: Any,
    settings: Settings,
    broker: BrokerPort,
    store: StateStore,
) -> None:
    event = getattr(data, "event", None) or (data.get("event") if isinstance(data, dict) else None)
    event_name = str(event).lower() if event else ""
    order_payload = _to_mapping(getattr(data, "order", None) or (data.get("order") if isinstance(data, dict) else None))
    if not order_payload:
        logger.warning("Trade update missing order payload: event=%s", event)
        return

    try:
        order = Order.from_alpaca(order_payload)
        store.upsert_order(settings.engine_profile_id, order, source="trade_update")
    except Exception:
        logger.exception("Failed to persist trade update order")

    if event_name == "fill":
        fill = _build_fill_from_order(order_payload)
        if fill:
            try:
                store.record_fill(settings.engine_profile_id, fill)
            except Exception:
                logger.exception("Failed to persist fill record")
        _auto_protect_on_fill(
            order_payload=order_payload,
            settings=settings,
            broker=broker,
            store=store,
        )


def run_trading_stream(
    settings: Settings,
    loop: asyncio.AbstractEventLoop,
    refresh_event: asyncio.Event,
    broker: BrokerPort,
    store: StateStore,
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
        process_trade_update(data, settings, broker, store)
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

        jitter = random.uniform(0, 0.5)  # noqa: S311
        time.sleep(backoff_seconds + jitter)
        backoff_seconds = min(backoff_seconds * 2, max_backoff)
