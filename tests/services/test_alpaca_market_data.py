from decimal import Decimal
from typing import Any, Dict, List

import pytest

from app.config import Settings
from app.services.alpaca_market_data import AlpacaMarketDataService


def _position_payload(symbol: str, quantity_key: str = "qty") -> Dict[str, Any]:
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
        self._positions: List[Any] = []

    def with_positions(self, positions: List[Any]) -> "DummyTradingClient":
        self._positions = positions
        return self

    def get_all_positions(self) -> List[Any]:
        return self._positions


def test_get_user_positions_converts_sdk_models(monkeypatch) -> None:
    created_clients: List[DummyTradingClient] = []

    def fake_trading_client(**kwargs: Any) -> DummyTradingClient:
        client = DummyTradingClient(**kwargs).with_positions(
            [
                DummySDKPosition(_position_payload("AAPL")),
                _position_payload("MSFT", quantity_key="quantity"),
            ]
        )
        created_clients.append(client)
        return client

    class DummySDKPosition:
        def __init__(self, payload: Dict[str, Any]) -> None:
            self._payload = payload

        def model_dump(self) -> Dict[str, Any]:
            return self._payload

    monkeypatch.setattr(
        "app.services.alpaca_market_data.TradingClient", fake_trading_client
    )
    monkeypatch.setenv("ALPACA_API_KEY", "key")
    monkeypatch.setenv("ALPACA_API_SECRET", "secret")
    monkeypatch.setenv("ALPACA_TRADING_BASE_URL", "https://paper-api.alpaca.markets")
    monkeypatch.setenv("ALPACA_PAPER_TRADING", "true")

    settings = Settings()
    service = AlpacaMarketDataService(settings)

    positions = service.get_user_positions()

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

        def get_all_positions(self) -> List[Any]:
            raise DummyAPIError("boom")

    monkeypatch.setattr(
        "app.services.alpaca_market_data.TradingClient", DummyTradingClient
    )
    monkeypatch.setattr("app.services.alpaca_market_data.APIError", DummyAPIError)
    monkeypatch.setenv("ALPACA_API_KEY", "key")
    monkeypatch.setenv("ALPACA_API_SECRET", "secret")

    settings = Settings()
    service = AlpacaMarketDataService(settings)

    with pytest.raises(RuntimeError) as excinfo:
        service.get_user_positions()

    assert "Failed to fetch positions" in str(excinfo.value)
