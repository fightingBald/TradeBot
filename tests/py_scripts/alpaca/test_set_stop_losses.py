from __future__ import annotations

from decimal import Decimal
from typing import Any, Dict, List

import pytest

from alpaca.trading.enums import OrderSide, OrderType, TimeInForce

from py_scripts.alpaca.set_stop_losses import (
    STOP_ORDER_PREFIX,
    apply_stop_losses,
    compute_stop_price,
)


class DummyOrder:
    def __init__(
        self, symbol: str, stop_price: float, client_order_id: str, order_id: str
    ):
        self.symbol = symbol
        self.stop_price = stop_price
        self.client_order_id = client_order_id
        self.id = order_id
        self.order_type = OrderType.STOP


class DummyTradingClient:
    def __init__(self, positions: List[Dict[str, Any]], open_orders: List[DummyOrder]):
        self._positions = positions
        self._orders = open_orders
        self.submitted: List[Dict[str, Any]] = []
        self.cancelled: List[str] = []

    def get_all_positions(self):
        return self._positions

    def get_orders(self, request):  # noqa: ARG002
        return self._orders

    def cancel_order_by_id(self, order_id: str):
        self.cancelled.append(order_id)

    def submit_order(self, order_request):
        self.submitted.append(
            {
                "symbol": order_request.symbol,
                "qty": order_request.qty,
                "stop_price": order_request.stop_price,
                "client_order_id": order_request.client_order_id,
                "side": order_request.side,
                "type": order_request.type,
                "time_in_force": order_request.time_in_force,
            }
        )


def _position(symbol: str, price: float) -> Dict[str, Any]:
    return {
        "symbol": symbol,
        "asset_id": f"id-{symbol}",
        "side": "long",
        "qty": "10",
        "avg_entry_price": "100",
        "market_value": str(price * 10),
        "cost_basis": "1000",
        "current_price": str(price),
    }


def test_compute_stop_price():
    stop = compute_stop_price(Decimal("100"), Decimal("0.03"))
    assert stop == Decimal("97.00")


def test_apply_stop_losses_submits_order_when_missing():
    client = DummyTradingClient(positions=[_position("AAPL", 110.0)], open_orders=[])
    apply_stop_losses(
        client, stop_pct=Decimal("0.03"), tolerance_pct=Decimal("0.005"), dry_run=False
    )
    assert client.submitted
    order = client.submitted[0]
    assert order["symbol"] == "AAPL"
    assert pytest.approx(order["stop_price"], rel=1e-6) == 106.7
    assert order["client_order_id"] == f"{STOP_ORDER_PREFIX}AAPL"
    assert order["side"] == OrderSide.SELL
    assert order["type"] == OrderType.STOP
    assert order["time_in_force"] == TimeInForce.GTC


def test_apply_stop_losses_skips_when_existing_within_tolerance():
    existing = DummyOrder(
        "AAPL",
        stop_price=106.9,
        client_order_id=f"{STOP_ORDER_PREFIX}AAPL",
        order_id="order-1",
    )
    client = DummyTradingClient(
        positions=[_position("AAPL", 110.0)], open_orders=[existing]
    )

    apply_stop_losses(
        client, stop_pct=Decimal("0.03"), tolerance_pct=Decimal("0.02"), dry_run=False
    )
    assert not client.cancelled
    assert not client.submitted


def test_apply_stop_losses_replaces_when_out_of_tolerance():
    existing = DummyOrder(
        "AAPL",
        stop_price=90.0,
        client_order_id=f"{STOP_ORDER_PREFIX}AAPL",
        order_id="order-1",
    )
    client = DummyTradingClient(
        positions=[_position("AAPL", 110.0)], open_orders=[existing]
    )

    apply_stop_losses(
        client, stop_pct=Decimal("0.03"), tolerance_pct=Decimal("0.005"), dry_run=False
    )

    assert client.cancelled == ["order-1"]
    assert len(client.submitted) == 1
