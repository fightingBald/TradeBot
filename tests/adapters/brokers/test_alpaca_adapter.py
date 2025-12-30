from __future__ import annotations

from types import SimpleNamespace

import pytest

import adapters.brokers.alpaca as adapter_mod
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

    monkeypatch.setattr(adapter_mod, "AlpacaBrokerService", DummyService)

    settings = SimpleNamespace()
    adapter = adapter_mod.AlpacaBrokerAdapter(settings)

    assert adapter.get_positions()[0].symbol == "AAPL"
    assert adapter.get_latest_quotes(["AAPL"])["AAPL"]["bid_price"] == 100.0
    assert adapter.cancel_open_orders() == ["cancelled"]
    assert adapter.close_all_positions(cancel_orders=False) == [{"cancel_orders": False}]
