from __future__ import annotations

import asyncio
import sys
import threading
import types
from types import SimpleNamespace

import pytest

import apps.engine.main as engine_main
from core.domain.commands import Command, CommandType
from core.domain.position import Position


class DummyBroker:
    def __init__(self, positions: list[Position] | None = None) -> None:
        self.positions = positions or []
        self.close_calls: list[bool | None] = []

    def get_positions(self) -> list[Position]:
        return list(self.positions)

    def close_all_positions(self, cancel_orders: bool | None = True) -> list[object]:
        self.close_calls.append(cancel_orders)
        return []


class DummyStore:
    def __init__(self, *_args, **_kwargs) -> None:
        self.upsert_calls: list[tuple[str, list[Position]]] = []
        self.closed = False

    def upsert_positions(self, profile_id: str, positions: list[Position]) -> None:
        self.upsert_calls.append((profile_id, list(positions)))

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

    asyncio.run(engine_main._handle_command(command, broker, store, profile_id="default"))

    assert broker.close_calls == []
    assert store.upsert_calls == []


def test_handle_command_executes_kill_switch() -> None:
    broker = DummyBroker()
    store = DummyStore()
    command = Command(type=CommandType.KILL_SWITCH, profile_id="default", payload={"reason": "risk"})

    asyncio.run(engine_main._handle_command(command, broker, store, profile_id="default"))

    assert broker.close_calls == [True]
    assert store.upsert_calls == [("default", [])]


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
    command_calls: list[tuple[object, object, object, str]] = []
    ws_called = threading.Event()

    async def fake_sync(context: engine_main.PositionSyncContext, _event: asyncio.Event) -> None:
        sync_calls.append(context)

    async def fake_command(bus: object, broker: object, store: object, profile_id: str) -> None:
        command_calls.append((bus, broker, store, profile_id))

    def fake_ws(*_args: object, **_kwargs: object) -> None:
        ws_called.set()

    class DummySettings:
        def __init__(self) -> None:
            self.engine_profile_id = "profile-1"
            self.engine_poll_interval_seconds = 5
            self.engine_sync_min_interval_seconds = 0
            self.engine_enable_trading_ws = enable_ws
            self.engine_trading_ws_max_backoff_seconds = 3
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
    monkeypatch.setattr(engine_main, "SqliteStateStore", fake_store)
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
    )

    def fake_sleep(_seconds: float) -> None:
        raise RuntimeError("stop")

    monkeypatch.setattr(engine_main.time, "sleep", fake_sleep)

    with pytest.raises(RuntimeError, match="stop"):
        engine_main._run_trading_stream(settings, loop, refresh_event)

    assert refresh_event.is_set()
    assert loop.called is True
