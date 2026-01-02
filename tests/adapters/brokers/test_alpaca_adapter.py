from __future__ import annotations

from types import SimpleNamespace

import pytest

import adapters.brokers.alpaca as adapter_mod
from core.domain.order import Order, OrderSide, TimeInForce, TrailingStopOrderRequest
from core.domain.position import Position


def test_alpaca_adapter_delegates_to_service(monkeypatch: pytest.MonkeyPatch) -> None:
    class DummyService:
        def __init__(self, settings: object) -> None:
            self.settings = settings

        def get_positions(self) -> list[Position]:
            return [
                Position(
                    symbol="AAPL",
                    asset_id="aapl-id",
                    side="long",
                    quantity="1",
                    avg_entry_price="10",
                    market_value="10",
                    cost_basis="10",
                )
            ]

        def get_latest_quotes(self, symbols: list[str]):
            return {"AAPL": {"bid_price": 100.0}}

        def cancel_open_orders(self):
            return ["cancelled"]

        def close_all_positions(self, cancel_orders: bool | None = True):
            return [{"cancel_orders": cancel_orders}]

        def submit_trailing_stop_order(self, order: TrailingStopOrderRequest) -> Order:
            return Order(
                order_id="order-1",
                client_order_id=order.client_order_id,
                symbol=order.symbol,
                side=order.side.value,
                order_type="trailing_stop",
                time_in_force=order.time_in_force.value,
                status="accepted",
                qty=order.qty,
                trail_percent=order.trail_percent,
            )

    monkeypatch.setattr(adapter_mod, "AlpacaBrokerService", DummyService)

    settings = SimpleNamespace()
    adapter = adapter_mod.AlpacaBrokerAdapter(settings)

    assert adapter.get_positions()[0].symbol == "AAPL"
    assert adapter.get_latest_quotes(["AAPL"])["AAPL"]["bid_price"] == 100.0
    assert adapter.cancel_open_orders() == ["cancelled"]
    assert adapter.close_all_positions(cancel_orders=False) == [{"cancel_orders": False}]
    order = adapter.submit_trailing_stop_order(
        TrailingStopOrderRequest(
            symbol="AAPL",
            side=OrderSide.BUY,
            qty="1",
            trail_percent="2",
            time_in_force=TimeInForce.DAY,
            extended_hours=False,
            client_order_id="client-1",
        )
    )
    assert order.order_id == "order-1"
