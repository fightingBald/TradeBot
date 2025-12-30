from decimal import Decimal
from typing import Any

import pytest

from adapters.brokers.alpaca_service import AlpacaBrokerService
from core.settings import Settings


def _position_payload(symbol: str, quantity_key: str = "qty") -> dict[str, Any]:
    quantity_value = "10" if symbol == "MSFT" else "5"
    payload = {
        "symbol": symbol,
        "asset_id": f"{symbol.lower()}-id",
        "asset_class": "us_equity",
        "exchange": "NASDAQ",
        "side": "long",
        "avg_entry_price": "123.45",
        "market_value": "617.25",
        "cost_basis": "612.25",
        "unrealized_pl": "5.00",
        "unrealized_plpc": "0.008",
        "current_price": "123.45",
        "lastday_price": "122.00",
        "change_today": "0.0119",
    }
    payload[quantity_key] = quantity_value
    return payload


class DummyTradingClient:
    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs
        self._positions: list[Any] = []

    def with_positions(self, positions: list[Any]) -> "DummyTradingClient":
        self._positions = positions
        return self

    def get_all_positions(self) -> list[Any]:
        return self._positions


def test_get_user_positions_converts_sdk_models(monkeypatch) -> None:
    created_clients: list[DummyTradingClient] = []

    def fake_trading_client(**kwargs: Any) -> DummyTradingClient:
        client = DummyTradingClient(**kwargs).with_positions(
            [DummySDKPosition(_position_payload("AAPL")), _position_payload("MSFT", quantity_key="quantity")]
        )
        created_clients.append(client)
        return client

    class DummySDKPosition:
        def __init__(self, payload: dict[str, Any]) -> None:
            self._payload = payload

        def model_dump(self) -> dict[str, Any]:
            return self._payload

    monkeypatch.setattr("adapters.brokers.alpaca_service.TradingClient", fake_trading_client)
    monkeypatch.setenv("ALPACA_API_KEY", "key")
    monkeypatch.setenv("ALPACA_API_SECRET", "secret")
    monkeypatch.setenv("ALPACA_TRADING_BASE_URL", "https://paper-api.alpaca.markets")
    monkeypatch.setenv("ALPACA_PAPER_TRADING", "true")

    settings = Settings()
    service = AlpacaBrokerService(settings)

    positions = service.get_positions()

    assert len(positions) == 2
    assert positions[0].symbol == "AAPL"
    assert positions[0].quantity == Decimal("5")
    assert positions[1].symbol == "MSFT"
    assert positions[1].quantity == Decimal("10")

    assert created_clients[0].kwargs["api_key"] == "key"
    assert created_clients[0].kwargs["secret_key"] == "secret"
    assert created_clients[0].kwargs["paper"] is settings.paper_trading
    assert created_clients[0].kwargs["base_url"] == settings.trading_base_url


def test_get_user_positions_wraps_api_errors(monkeypatch) -> None:
    class DummyAPIError(Exception):
        pass

    class DummyTradingClient:
        def __init__(self, **_: Any) -> None:
            pass

        def get_all_positions(self) -> list[Any]:
            raise DummyAPIError("boom")

    monkeypatch.setattr("adapters.brokers.alpaca_service.TradingClient", DummyTradingClient)
    monkeypatch.setattr("adapters.brokers.alpaca_service.APIError", DummyAPIError)
    monkeypatch.setenv("ALPACA_API_KEY", "key")
    monkeypatch.setenv("ALPACA_API_SECRET", "secret")

    settings = Settings()
    service = AlpacaBrokerService(settings)

    with pytest.raises(RuntimeError) as excinfo:
        service.get_positions()

    assert "Failed to fetch positions" in str(excinfo.value)


def test_cancel_open_orders_wraps_api_errors(monkeypatch) -> None:
    class DummyAPIError(Exception):
        pass

    class DummyTradingClient:
        def __init__(self, **_: Any) -> None:
            pass

        def cancel_orders(self) -> list[Any]:
            raise DummyAPIError("boom")

        def get_all_positions(self) -> list[Any]:
            return []

    monkeypatch.setattr("adapters.brokers.alpaca_service.TradingClient", DummyTradingClient)
    monkeypatch.setattr("adapters.brokers.alpaca_service.APIError", DummyAPIError)
    monkeypatch.setenv("ALPACA_API_KEY", "key")
    monkeypatch.setenv("ALPACA_API_SECRET", "secret")

    settings = Settings()
    service = AlpacaBrokerService(settings)

    with pytest.raises(RuntimeError) as excinfo:
        service.cancel_open_orders()

    assert "Failed to cancel orders" in str(excinfo.value)


def test_close_all_positions_passes_cancel_orders(monkeypatch) -> None:
    created_clients: list[Any] = []

    class DummyTradingClient:
        def __init__(self, **_: Any) -> None:
            self.cancel_orders_value: bool | None = None
            created_clients.append(self)

        def close_all_positions(self, cancel_orders: bool | None = None) -> list[Any]:
            self.cancel_orders_value = cancel_orders
            return []

        def get_all_positions(self) -> list[Any]:
            return []

    monkeypatch.setattr("adapters.brokers.alpaca_service.TradingClient", DummyTradingClient)
    monkeypatch.setenv("ALPACA_API_KEY", "key")
    monkeypatch.setenv("ALPACA_API_SECRET", "secret")

    settings = Settings()
    service = AlpacaBrokerService(settings)

    service.close_all_positions(cancel_orders=False)

    assert created_clients[0].cancel_orders_value is False


def test_close_all_positions_wraps_api_errors(monkeypatch) -> None:
    class DummyAPIError(Exception):
        pass

    class DummyTradingClient:
        def __init__(self, **_: Any) -> None:
            pass

        def close_all_positions(self, cancel_orders: bool | None = None) -> list[Any]:
            raise DummyAPIError("boom")

        def get_all_positions(self) -> list[Any]:
            return []

    monkeypatch.setattr("adapters.brokers.alpaca_service.TradingClient", DummyTradingClient)
    monkeypatch.setattr("adapters.brokers.alpaca_service.APIError", DummyAPIError)
    monkeypatch.setenv("ALPACA_API_KEY", "key")
    monkeypatch.setenv("ALPACA_API_SECRET", "secret")

    settings = Settings()
    service = AlpacaBrokerService(settings)

    with pytest.raises(RuntimeError) as excinfo:
        service.close_all_positions()

    assert "Failed to close positions" in str(excinfo.value)
