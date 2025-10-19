from decimal import Decimal

import pytest

from app.models.user_position import UserPosition


def _position_payload(symbol: str = "AAPL", qty: str = "5") -> dict:
    return {
        "symbol": symbol,
        "asset_id": f"{symbol.lower()}-id",
        "asset_class": "us_equity",
        "exchange": "NASDAQ",
        "side": "long",
        "qty": qty,
        "avg_entry_price": "123.45",
        "market_value": "617.25",
        "cost_basis": "612.25",
        "unrealized_pl": "5.00",
        "unrealized_plpc": "0.008",
        "current_price": "123.45",
        "lastday_price": "122.00",
        "change_today": "0.0119",
    }


class DummySDKPosition:
    def __init__(self, payload: dict) -> None:
        self._payload = payload

    def model_dump(self) -> dict:
        return self._payload


def test_from_alpaca_accepts_sdk_objects() -> None:
    payload = _position_payload()
    sdk_position = DummySDKPosition(payload)

    result = UserPosition.from_alpaca(sdk_position)

    assert result.symbol == "AAPL"
    assert result.quantity == Decimal("5")
    assert result.avg_entry_price == Decimal("123.45")


def test_from_alpaca_accepts_plain_dicts() -> None:
    payload = _position_payload(symbol="MSFT")

    result = UserPosition.from_alpaca(payload)

    assert result.symbol == "MSFT"
    assert result.quantity == Decimal("5")


def test_from_alpaca_rejects_unknown_objects() -> None:
    with pytest.raises(TypeError):
        UserPosition.from_alpaca(object())
