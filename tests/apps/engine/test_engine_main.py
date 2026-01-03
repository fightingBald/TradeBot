from __future__ import annotations

import asyncio
import sys
import threading
import types
from decimal import Decimal
from types import SimpleNamespace

import pytest

import apps.engine.main as engine_main
import apps.engine.streams as engine_streams
from core.domain.commands import Command, CommandType
from core.domain.order import Order, OrderSide, TimeInForce, TrailingStopOrderRequest
from core.domain.position import Position


class DummyBroker:
    def __init__(self, positions: list[Position] | None = None) -> None:
        self.positions = positions or []
        self.close_calls: list[bool | None] = []
        self.trailing_calls: list[TrailingStopOrderRequest] = []

    def get_positions(self) -> list[Position]:
        return list(self.positions)

    def close_all_positions(self, cancel_orders: bool | None = True) -> list[object]:
        self.close_calls.append(cancel_orders)
        return []

    def submit_trailing_stop_order(self, order: TrailingStopOrderRequest) -> Order:
        self.trailing_calls.append(order)
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


class DummyStore:
    def __init__(self, *_args, **_kwargs) -> None:
        self.upsert_calls: list[tuple[str, list[Position]]] = []
        self.order_calls: list[tuple[str, Order, str | None]] = []
        self.positions: list[Position] = []
        self.protection_links: set[str] = set()
        self.closed = False

    def upsert_positions(self, profile_id: str, positions: list[Position]) -> None:
        self.upsert_calls.append((profile_id, list(positions)))
        self.positions = list(positions)

    def list_positions(self, _profile_id: str) -> list[Position]:
        return list(self.positions)

    def upsert_order(self, profile_id: str, order: Order, *, source: str | None = None) -> None:
        self.order_calls.append((profile_id, order, source))

    def list_orders(self, _profile_id: str, *, limit: int = 100) -> list[Order]:
        return [call[1] for call in self.order_calls][-limit:]

    def record_fill(self, _profile_id: str, _fill: object) -> None:
        return None

    def list_fills(self, _profile_id: str, *, limit: int = 100) -> list[object]:
        return []

    def has_protection_link(self, _profile_id: str, entry_order_id: str) -> bool:
        return entry_order_id in self.protection_links

    def create_protection_link(self, _profile_id: str, entry_order_id: str, _protection_order_id: str) -> None:
        self.protection_links.add(entry_order_id)

    def close(self) -> None:
        self.closed = True


class DummyBus:
    def __init__(self, *_args, **_kwargs) -> None:
        self.closed = False

    async def close(self) -> None:
        self.closed = True


def test_handle_command_ignores_other_profile() -> None:
    broker = DummyBroker()
    store = DummyStore()
    command = Command(type=CommandType.KILL_SWITCH, profile_id="other", payload={})
    settings = SimpleNamespace(engine_profile_id="default")

    asyncio.run(engine_main._handle_command(command, broker, store, settings))

    assert broker.close_calls == []
    assert store.upsert_calls == []


def test_handle_command_executes_kill_switch() -> None:
    broker = DummyBroker()
    store = DummyStore()
    command = Command(type=CommandType.KILL_SWITCH, profile_id="default", payload={"reason": "risk"})
    settings = SimpleNamespace(engine_profile_id="default")

    asyncio.run(engine_main._handle_command(command, broker, store, settings))

    assert broker.close_calls == [True]
    assert store.upsert_calls == [("default", [])]


def test_handle_command_trailing_stop_buy_submits_order() -> None:
    broker = DummyBroker()
    store = DummyStore()
    command = Command(
        type=CommandType.TRAILING_STOP_BUY,
        profile_id="default",
        payload={"symbol": "AAPL", "qty": 1, "trail_percent": 2},
    )
    settings = SimpleNamespace(
        engine_profile_id="default",
        engine_trailing_default_percent=2.0,
        engine_trailing_buy_tif="day",
        engine_trailing_sell_tif="gtc",
    )

    asyncio.run(engine_main._handle_command(command, broker, store, settings))

    assert broker.trailing_calls
    assert store.order_calls
    assert broker.trailing_calls[0].side is OrderSide.BUY


def test_handle_command_trailing_stop_sell_uses_position_qty() -> None:
    broker = DummyBroker()
    store = DummyStore()
    store.positions = [
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
    command = Command(
        type=CommandType.TRAILING_STOP_SELL,
        profile_id="default",
        payload={"symbol": "AAPL"},
    )
    settings = SimpleNamespace(
        engine_profile_id="default",
        engine_trailing_default_percent=2.0,
        engine_trailing_buy_tif="day",
        engine_trailing_sell_tif="gtc",
    )

    asyncio.run(engine_main._handle_command(command, broker, store, settings))

    assert broker.trailing_calls
    assert broker.trailing_calls[0].side is OrderSide.SELL
    assert broker.trailing_calls[0].qty == Decimal("2")


def test_handle_command_trailing_stop_sell_fractional_forces_day_tif() -> None:
    broker = DummyBroker()
    store = DummyStore()
    store.positions = [
        Position(
            symbol="AAPL",
            asset_id="aapl-id",
            side="long",
            quantity="1.5",
            avg_entry_price="10",
            market_value="15",
            cost_basis="15",
        )
    ]
    command = Command(
        type=CommandType.TRAILING_STOP_SELL,
        profile_id="default",
        payload={"symbol": "AAPL"},
    )
    settings = SimpleNamespace(
        engine_profile_id="default",
        engine_trailing_default_percent=2.0,
        engine_trailing_buy_tif="day",
        engine_trailing_sell_tif="gtc",
    )

    asyncio.run(engine_main._handle_command(command, broker, store, settings))

    assert broker.trailing_calls
    assert broker.trailing_calls[0].time_in_force is TimeInForce.DAY


def test_sync_positions_loop_triggers_on_event() -> None:
    async def _run() -> None:
        refresh_event = asyncio.Event()
        sync_event = asyncio.Event()
        positions = [
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
        broker = DummyBroker(positions=positions)

        class RecordingStore(DummyStore):
            def upsert_positions(self, profile_id: str, positions: list[Position]) -> None:
                super().upsert_positions(profile_id, positions)
                sync_event.set()

        store = RecordingStore()
        context = engine_main.PositionSyncContext(
            broker=broker,
            store=store,
            profile_id="default",
            interval_seconds=5,
            min_interval_seconds=0,
        )

        refresh_event.set()
        task = asyncio.create_task(engine_main._sync_positions_loop(context, refresh_event))
        await asyncio.wait_for(sync_event.wait(), timeout=1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

        assert store.upsert_calls == [("default", positions)]

    asyncio.run(_run())


@pytest.mark.parametrize("enable_ws", [True, False], ids=["ws_on", "ws_off"])
def test_run_engine_runs_tasks_and_cleans_up(monkeypatch: pytest.MonkeyPatch, enable_ws: bool) -> None:
    sync_calls: list[engine_main.PositionSyncContext] = []
    command_calls: list[tuple[object, object, object, object]] = []
    ws_called = threading.Event()

    async def fake_sync(context: engine_main.PositionSyncContext, _event: asyncio.Event) -> None:
        sync_calls.append(context)

    async def fake_command(bus: object, broker: object, store: object, settings: object) -> None:
        command_calls.append((bus, broker, store, settings))

    def fake_ws(*_args: object, **_kwargs: object) -> None:
        ws_called.set()

    class DummySettings:
        def __init__(self) -> None:
            self.engine_profile_id = "profile-1"
            self.engine_poll_interval_seconds = 5
            self.engine_sync_min_interval_seconds = 0
            self.engine_enable_trading_ws = enable_ws
            self.engine_trading_ws_max_backoff_seconds = 3
            self.engine_trailing_default_percent = 2.0
            self.engine_trailing_buy_tif = "day"
            self.engine_trailing_sell_tif = "gtc"
            self.engine_auto_protect_enabled = True
            self.engine_auto_protect_order_types = ["market"]
            self.database_url = "sqlite:///./data/engine.db"
            self.redis_url = "redis://localhost:6379/0"
            self.command_queue_name = "alpaca:commands"
            self.api_key = "key"
            self.api_secret = "secret"
            self.paper_trading = True

    created: dict[str, object] = {}

    def fake_broker(settings: DummySettings) -> DummyBroker:
        created["broker"] = DummyBroker()
        return created["broker"]  # type: ignore[return-value]

    def fake_store(_url: str) -> DummyStore:
        created["store"] = DummyStore()
        return created["store"]  # type: ignore[return-value]

    def fake_bus(_url: str, _name: str) -> DummyBus:
        created["bus"] = DummyBus()
        return created["bus"]  # type: ignore[return-value]

    monkeypatch.setattr(engine_main, "Settings", DummySettings)
    monkeypatch.setattr(engine_main, "AlpacaBrokerAdapter", fake_broker)
    monkeypatch.setattr(engine_main, "SqlAlchemyStateStore", fake_store)
    monkeypatch.setattr(engine_main, "RedisCommandBus", fake_bus)
    monkeypatch.setattr(engine_main, "_sync_positions_loop", fake_sync)
    monkeypatch.setattr(engine_main, "_command_loop", fake_command)
    monkeypatch.setattr(engine_main, "_run_trading_stream", fake_ws)

    asyncio.run(engine_main.run_engine())

    assert sync_calls
    assert command_calls
    assert created["store"].closed is True
    assert created["bus"].closed is True
    assert ws_called.is_set() is enable_ws


def test_run_trading_stream_sets_refresh_event(monkeypatch: pytest.MonkeyPatch) -> None:
    class DummyStream:
        def __init__(self, *_args, **_kwargs) -> None:
            self.handler: object | None = None

        def subscribe_trade_updates(self, handler: object) -> None:
            self.handler = handler

        def run(self) -> None:
            assert self.handler is not None
            asyncio.run(self.handler(SimpleNamespace(event="fill")))

    stream_module = types.ModuleType("alpaca.trading.stream")
    stream_module.TradingStream = DummyStream
    monkeypatch.setitem(sys.modules, "alpaca.trading.stream", stream_module)

    class DummyLoop:
        def __init__(self) -> None:
            self.called = False

        def call_soon_threadsafe(self, func: object, *args: object) -> None:
            self.called = True
            func(*args)

    refresh_event = asyncio.Event()
    loop = DummyLoop()
    settings = SimpleNamespace(
        api_key="key",
        api_secret="secret",
        paper_trading=True,
        engine_trading_ws_max_backoff_seconds=1,
        engine_profile_id="default",
        engine_trailing_default_percent=2.0,
        engine_trailing_sell_tif="gtc",
        engine_auto_protect_enabled=True,
        engine_auto_protect_order_types=["market"],
    )

    def fake_sleep(_seconds: float) -> None:
        raise RuntimeError("stop")

    monkeypatch.setattr(engine_streams.time, "sleep", fake_sleep)

    with pytest.raises(RuntimeError, match="stop"):
        engine_main._run_trading_stream(settings, loop, refresh_event, DummyBroker(), DummyStore())

    assert refresh_event.is_set()
    assert loop.called is True
