from __future__ import annotations

from typing import ClassVar

import pytest
from fastapi.testclient import TestClient

import apps.api.main as api_main
from core.domain.commands import CommandType
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


def _build_client(
    monkeypatch: pytest.MonkeyPatch,
    *,
    paper: bool = True,
    profile_id: str = "default",
    positions: list[Position] | None = None,
) -> TestClient:
    DummyStateStore.positions = positions or []
    monkeypatch.setattr(api_main, "SqliteStateStore", DummyStateStore)
    monkeypatch.setattr(api_main, "RedisCommandBus", DummyCommandBus)
    monkeypatch.setenv("ALPACA_API_KEY", "key")
    monkeypatch.setenv("ALPACA_API_SECRET", "secret")
    monkeypatch.setenv("ALPACA_PAPER_TRADING", "true" if paper else "false")
    monkeypatch.setenv("ENGINE_PROFILE_ID", profile_id)
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
