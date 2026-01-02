from __future__ import annotations

from decimal import Decimal

from adapters.storage.sqlalchemy_state_store import SqlAlchemyStateStore
from core.domain.order import Fill, Order
from core.domain.position import Position


def _position(symbol: str, market_value: str, quantity: str) -> Position:
    return Position(
        symbol=symbol,
        asset_id=f"{symbol.lower()}-id",
        asset_class="us_equity",
        exchange="NASDAQ",
        side="long",
        quantity=quantity,
        avg_entry_price="100",
        market_value=market_value,
        cost_basis=market_value,
    )


def test_upsert_and_list_positions(tmp_path) -> None:
    db_path = tmp_path / "engine.db"
    store = SqlAlchemyStateStore(f"sqlite:///{db_path}")

    positions = [
        _position("AAPL", market_value="200", quantity="2"),
        _position("MSFT", market_value="100", quantity="1"),
    ]

    store.upsert_positions("alpha", positions)
    results = store.list_positions("alpha")

    assert [item.symbol for item in results] == ["AAPL", "MSFT"]
    assert results[0].market_value == Decimal("200")

    store.upsert_positions("alpha", [positions[1]])
    refreshed = store.list_positions("alpha")

    assert [item.symbol for item in refreshed] == ["MSFT"]

    store.close()


def test_upsert_accepts_long_symbol(tmp_path) -> None:
    db_path = tmp_path / "engine.db"
    store = SqlAlchemyStateStore(f"sqlite:///{db_path}")

    long_symbol = "ORCL260618C00200000"
    store.upsert_positions("alpha", [_position(long_symbol, market_value="5020", quantity="2")])

    results = store.list_positions("alpha")

    assert results[0].symbol == long_symbol

    store.close()


def test_upsert_and_list_orders_and_fills(tmp_path) -> None:
    db_path = tmp_path / "engine.db"
    store = SqlAlchemyStateStore(f"sqlite:///{db_path}")

    order = Order(
        order_id="order-1",
        client_order_id="client-1",
        symbol="AAPL",
        side="buy",
        order_type="trailing_stop",
        time_in_force="day",
        status="accepted",
        qty="1",
        filled_qty="0",
        trail_percent="2",
    )
    store.upsert_order("alpha", order, source="ui")

    refreshed = store.list_orders("alpha")
    assert refreshed[0].order_id == "order-1"
    assert refreshed[0].trail_percent == Decimal("2")

    fill = Fill(order_id="order-1", symbol="AAPL", side="buy", qty="1", price="101.5")
    store.record_fill("alpha", fill)

    fills = store.list_fills("alpha")
    assert fills[0].order_id == "order-1"
    assert fills[0].price == Decimal("101.5")

    assert store.has_protection_link("alpha", "order-1") is False
    store.create_protection_link("alpha", "order-1", "order-2")
    assert store.has_protection_link("alpha", "order-1") is True

    store.close()
