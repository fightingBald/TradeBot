from __future__ import annotations

from decimal import Decimal

from core.domain.order import Order


def test_order_from_alpaca_handles_aliases() -> None:
    payload = {
        "id": "order-1",
        "client_order_id": "client-1",
        "symbol": "AAPL",
        "side": "OrderSide.BUY",
        "type": "trailing_stop",
        "time_in_force": "TimeInForce.DAY",
        "status": "accepted",
        "qty": "1",
        "filled_qty": "0",
        "filled_avg_price": "0",
        "trail_percent": "2",
    }

    order = Order.from_alpaca(payload)

    assert order.order_id == "order-1"
    assert order.client_order_id == "client-1"
    assert order.order_type == "trailing_stop"
    assert order.side == "buy"
    assert order.time_in_force == "day"
    assert order.qty == Decimal("1")
    assert order.trail_percent == Decimal("2")
