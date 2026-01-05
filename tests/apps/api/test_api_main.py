from __future__ import annotations

from typing import ClassVar

import pytest
from fastapi.testclient import TestClient

import apps.api.main as api_main
from core.domain.commands import CommandType
from core.domain.market_data import BarSnapshot, QuoteSnapshot, TradeSnapshot
from core.domain.position import Position


class DummyStateStore:
    positions: ClassVar[list[Position]] = []

    def __init__(self, *_args, **_kwargs) -> None:
        self.last_profile_id: str | None = None

    def list_positions(self, profile_id: str) -> list[Position]:
        self.last_profile_id = profile_id
        return list(self.positions)

    def close(self) -> None:
        return None


class DummyCommandBus:
    def __init__(self, *_args, **_kwargs) -> None:
        self.published: list[object] = []

    async def publish(self, command: object) -> None:
        self.published.append(command)

    async def close(self) -> None:
        return None


class DummyMarketDataCache:
    watchlist: ClassVar[list[str]] = []
    quotes: ClassVar[dict[str, QuoteSnapshot]] = {}
    trades: ClassVar[dict[str, TradeSnapshot]] = {}
    bars: ClassVar[dict[str, list[BarSnapshot]]] = {}

    def __init__(self, *_args, **_kwargs) -> None:
        return None

    async def set_watchlist(self, _profile_id: str, symbols: list[str]) -> None:
        self.watchlist = list(symbols)

    async def get_watchlist(self, _profile_id: str) -> list[str]:
        return list(self.watchlist)

    async def get_latest_quotes(self, _profile_id: str, symbols: list[str]) -> dict[str, QuoteSnapshot]:
        return {symbol: self.quotes[symbol] for symbol in symbols if symbol in self.quotes}

    async def get_latest_trades(self, _profile_id: str, symbols: list[str]) -> dict[str, TradeSnapshot]:
        return {symbol: self.trades[symbol] for symbol in symbols if symbol in self.trades}

    async def get_recent_bars(
        self, _profile_id: str, symbols: list[str], *, limit: int, timeframe: str = "1Min"
    ) -> dict[str, list[BarSnapshot]]:
        _ = timeframe
        results: dict[str, list[BarSnapshot]] = {}
        for symbol in symbols:
            bars = self.bars.get(symbol, [])
            results[symbol] = bars[:limit]
        return results

    async def close(self) -> None:
        return None


def _build_client(
    monkeypatch: pytest.MonkeyPatch,
    *,
    paper: bool = True,
    profile_id: str = "default",
    positions: list[Position] | None = None,
    market_watchlist: list[str] | None = None,
    market_quotes: dict[str, QuoteSnapshot] | None = None,
    market_trades: dict[str, TradeSnapshot] | None = None,
    market_bars: dict[str, list[BarSnapshot]] | None = None,
) -> TestClient:
    DummyStateStore.positions = positions or []
    DummyMarketDataCache.watchlist = market_watchlist or []
    DummyMarketDataCache.quotes = market_quotes or {}
    DummyMarketDataCache.trades = market_trades or {}
    DummyMarketDataCache.bars = market_bars or {}
    monkeypatch.setattr(api_main, "SqlAlchemyStateStore", DummyStateStore)
    monkeypatch.setattr(api_main, "RedisCommandBus", DummyCommandBus)
    monkeypatch.setattr(api_main, "RedisMarketDataCache", DummyMarketDataCache)
    monkeypatch.setenv("ALPACA_API_KEY", "key")
    monkeypatch.setenv("ALPACA_API_SECRET", "secret")
    monkeypatch.setenv("ALPACA_PAPER_TRADING", "true" if paper else "false")
    monkeypatch.setenv("ENGINE_PROFILE_ID", profile_id)
    monkeypatch.setenv("MARKETDATA_SYMBOLS", "AAPL,MSFT")
    return TestClient(api_main.app)


def test_healthcheck_returns_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    with _build_client(monkeypatch) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.parametrize(
    ("paper", "expected_env"),
    [(True, "paper"), (False, "live")],
    ids=["paper", "live"],
)
def test_read_profile_reflects_environment(
    monkeypatch: pytest.MonkeyPatch, paper: bool, expected_env: str
) -> None:
    with _build_client(monkeypatch, paper=paper, profile_id="alpha") as client:
        response = client.get("/state/profile")

    assert response.status_code == 200
    assert response.json() == {"profile_id": "alpha", "environment": expected_env}


def test_read_positions_uses_profile_override(monkeypatch: pytest.MonkeyPatch) -> None:
    positions = [
        Position(
            symbol="AAPL",
            asset_id="aapl-id",
            side="long",
            quantity="1",
            avg_entry_price="10",
            market_value="10",
            cost_basis="10",
        ),
        Position(
            symbol="MSFT",
            asset_id="msft-id",
            side="long",
            quantity="2",
            avg_entry_price="5",
            market_value="10",
            cost_basis="10",
        ),
    ]
    with _build_client(monkeypatch, positions=positions) as client:
        response = client.get("/state/positions", params={"profile_id": "override"})

    assert response.status_code == 200
    payload = response.json()
    assert {item["symbol"] for item in payload} == {"AAPL", "MSFT"}
    assert client.app.state.state_store.last_profile_id == "override"


def test_kill_switch_rejects_invalid_token(monkeypatch: pytest.MonkeyPatch) -> None:
    with _build_client(monkeypatch, paper=True) as client:
        response = client.post(
            "/commands/kill-switch",
            json={"profile_id": "default", "confirm_token": "LIVE", "reason": "test"},
        )

    assert response.status_code == 400
    assert response.json()["detail"] == "Invalid confirmation token"


def test_kill_switch_publishes_command(monkeypatch: pytest.MonkeyPatch) -> None:
    with _build_client(monkeypatch, paper=True) as client:
        response = client.post(
            "/commands/kill-switch",
            json={"profile_id": "default", "confirm_token": "PAPER", "reason": "risk_off"},
        )

    assert response.status_code == 202
    command = client.app.state.command_bus.published[0]
    assert command.type is CommandType.KILL_SWITCH
    assert command.profile_id == "default"
    assert command.payload["reason"] == "risk_off"


def test_draft_and_confirm_publish_commands(monkeypatch: pytest.MonkeyPatch) -> None:
    with _build_client(monkeypatch) as client:
        draft_response = client.post(
            "/commands/draft",
            json={"profile_id": "default", "symbol": "AAPL", "side": "buy", "qty": 1, "order_type": "stop"},
        )
        confirm_response = client.post("/commands/confirm", json={"profile_id": "default", "draft_id": "draft-1"})

    assert draft_response.status_code == 202
    assert confirm_response.status_code == 202
    published = client.app.state.command_bus.published
    assert [cmd.type for cmd in published] == [CommandType.DRAFT_ORDER, CommandType.CONFIRM_ORDER]


def test_trailing_stop_endpoints_publish_commands(monkeypatch: pytest.MonkeyPatch) -> None:
    with _build_client(monkeypatch) as client:
        buy_response = client.post(
            "/commands/trailing-stop-buy",
            json={"profile_id": "default", "symbol": "AAPL", "qty": 1, "trail_percent": 2},
        )
        sell_response = client.post(
            "/commands/trailing-stop-loss",
            json={"profile_id": "default", "symbol": "AAPL"},
        )

    assert buy_response.status_code == 202
    assert sell_response.status_code == 202
    published = client.app.state.command_bus.published
    assert [cmd.type for cmd in published][-2:] == [CommandType.TRAILING_STOP_BUY, CommandType.TRAILING_STOP_SELL]


def test_market_data_watchlist_reads_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    with _build_client(monkeypatch, market_watchlist=["AAPL", "MSFT"]) as client:
        response = client.get("/market-data/watchlist")

    assert response.status_code == 200
    assert response.json() == ["AAPL", "MSFT"]


def test_market_data_endpoints_return_cached_data(monkeypatch: pytest.MonkeyPatch) -> None:
    quotes = {"AAPL": QuoteSnapshot(symbol="AAPL", bid_price="100", ask_price="101")}
    trades = {"AAPL": TradeSnapshot(symbol="AAPL", price="100.5", size="10")}
    bars = {
        "AAPL": [
            BarSnapshot(symbol="AAPL", timeframe="1Min", open="100", high="101", low="99", close="100.5", volume="50")
        ]
    }

    with _build_client(
        monkeypatch,
        market_watchlist=["AAPL"],
        market_quotes=quotes,
        market_trades=trades,
        market_bars=bars,
    ) as client:
        quotes_response = client.get("/market-data/quotes", params={"symbols": "AAPL"})
        trades_response = client.get("/market-data/trades", params={"symbols": "AAPL"})
        bars_response = client.get("/market-data/bars", params={"symbols": "AAPL", "limit": 10})

    assert quotes_response.status_code == 200
    assert trades_response.status_code == 200
    assert bars_response.status_code == 200
    assert quotes_response.json()["AAPL"]["bid_price"] == "100"
    assert trades_response.json()["AAPL"]["price"] == "100.5"
    assert bars_response.json()["AAPL"][0]["open"] == "100"
