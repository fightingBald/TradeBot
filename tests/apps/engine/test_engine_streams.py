from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

from apps.engine.streams import process_trade_update
from core.domain.order import Order, OrderSide, TimeInForce, TrailingStopOrderRequest
from core.domain.position import Position


class DummyBroker:
    def __init__(self) -> None:
        self.positions = [
            Position(
                symbol="AAPL",
                asset_id="aapl-id",
                side="long",
                quantity="2",
                avg_entry_price="10",
                market_value="20",
                cost_basis="20",
            )
        ]
        self.trailing_calls: list[TrailingStopOrderRequest] = []

    def get_positions(self) -> list[Position]:
        return list(self.positions)

    def submit_trailing_stop_order(self, order: TrailingStopOrderRequest) -> Order:
        self.trailing_calls.append(order)
        return Order(
            order_id="protect-1",
            client_order_id=order.client_order_id,
            symbol=order.symbol,
            side=order.side.value,
            order_type="trailing_stop",
            time_in_force=order.time_in_force.value,
            status="accepted",
            qty=order.qty,
            trail_percent=order.trail_percent,
        )


class DummyStore:
    def __init__(self) -> None:
        self.orders: list[Order] = []
        self.protection_links: set[str] = set()

    def upsert_order(self, _profile_id: str, order: Order, *, source: str | None = None) -> None:
        self.orders.append(order)

    def record_fill(self, _profile_id: str, _fill: object) -> None:
        return None

    def has_protection_link(self, _profile_id: str, entry_order_id: str) -> bool:
        return entry_order_id in self.protection_links

    def create_protection_link(self, _profile_id: str, entry_order_id: str, _protection_order_id: str) -> None:
        self.protection_links.add(entry_order_id)


def test_process_trade_update_creates_auto_protect_order() -> None:
    settings = SimpleNamespace(
        engine_profile_id="default",
        engine_auto_protect_enabled=True,
        engine_auto_protect_order_types=["market"],
        engine_trailing_default_percent=2.0,
        engine_trailing_sell_tif="gtc",
    )
    broker = DummyBroker()
    store = DummyStore()
    data = SimpleNamespace(
        event="fill",
        order={
            "id": "order-1",
            "symbol": "AAPL",
            "side": "OrderSide.BUY",
            "type": "market",
            "order_class": "simple",
            "filled_qty": "2",
            "filled_avg_price": "101.5",
            "status": "filled",
        },
    )

    process_trade_update(data, settings, broker, store)

    assert store.protection_links == {"order-1"}
    assert broker.trailing_calls
    assert broker.trailing_calls[0].side is OrderSide.SELL
    assert broker.trailing_calls[0].qty == Decimal("2")
    assert broker.trailing_calls[0].time_in_force is TimeInForce.GTC


def test_process_trade_update_skips_bracket_order() -> None:
    settings = SimpleNamespace(
        engine_profile_id="default",
        engine_auto_protect_enabled=True,
        engine_auto_protect_order_types=["market"],
        engine_trailing_default_percent=2.0,
        engine_trailing_sell_tif="gtc",
    )
    broker = DummyBroker()
    store = DummyStore()
    data = SimpleNamespace(
        event="fill",
        order={
            "id": "order-2",
            "symbol": "AAPL",
            "side": "buy",
            "type": "market",
            "order_class": "bracket",
            "filled_qty": "2",
            "filled_avg_price": "101.5",
            "status": "filled",
        },
    )

    process_trade_update(data, settings, broker, store)

    assert store.protection_links == set()
    assert broker.trailing_calls == []


def test_process_trade_update_fractional_qty_forces_day_tif() -> None:
    settings = SimpleNamespace(
        engine_profile_id="default",
        engine_auto_protect_enabled=True,
        engine_auto_protect_order_types=["market"],
        engine_trailing_default_percent=2.0,
        engine_trailing_sell_tif="gtc",
    )
    broker = DummyBroker()
    broker.positions[0].quantity = Decimal("1.5")
    store = DummyStore()
    data = SimpleNamespace(
        event="fill",
        order={
            "id": "order-3",
            "symbol": "AAPL",
            "side": "OrderSide.BUY",
            "type": "market",
            "order_class": "simple",
            "filled_qty": "1.5",
            "filled_avg_price": "101.5",
            "status": "filled",
        },
    )

    process_trade_update(data, settings, broker, store)

    assert broker.trailing_calls
    assert broker.trailing_calls[0].time_in_force is TimeInForce.DAY
