from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Any

from pydantic import AliasChoices, BaseModel, ConfigDict, Field


class OrderSide(str, Enum):
    BUY = "buy"
    SELL = "sell"


class TimeInForce(str, Enum):
    DAY = "day"
    GTC = "gtc"


class Order(BaseModel):
    """Domain model representing a broker order."""

    order_id: str = Field(validation_alias=AliasChoices("id", "order_id"))
    client_order_id: str | None = None
    symbol: str
    side: str
    order_type: str = Field(validation_alias=AliasChoices("type", "order_type"))
    time_in_force: str | None = None
    status: str | None = None
    qty: Decimal | None = Field(default=None, validation_alias=AliasChoices("qty", "quantity"))
    filled_qty: Decimal | None = Field(default=None, validation_alias=AliasChoices("filled_qty", "filled_quantity"))
    filled_avg_price: Decimal | None = None
    trail_percent: Decimal | None = None
    submitted_at: datetime | None = None
    updated_at: datetime | None = None
    order_class: str | None = None
    legs: list[Any] | None = None
    stop_loss: Any | None = None
    take_profit: Any | None = None

    model_config = ConfigDict(populate_by_name=True, arbitrary_types_allowed=False)

    @classmethod
    def from_alpaca(cls, order: Any) -> Order:
        if hasattr(order, "model_dump"):
            raw: dict[str, Any] = order.model_dump()
        elif hasattr(order, "dict"):
            raw = order.dict()
        elif isinstance(order, dict):
            raw = order
        else:
            raise TypeError(f"Unsupported order type: {type(order)!r}")

        if "order_id" not in raw and "id" in raw:
            raw["order_id"] = str(raw["id"])
        if "order_type" not in raw and "type" in raw:
            raw["order_type"] = raw["type"]
        if "quantity" not in raw and "qty" in raw:
            raw["quantity"] = raw["qty"]
        if "side" in raw:
            raw["side"] = _normalize_enum_text(raw["side"])
        if "order_type" in raw:
            raw["order_type"] = _normalize_enum_text(raw["order_type"])
        if "time_in_force" in raw and raw["time_in_force"] is not None:
            raw["time_in_force"] = _normalize_enum_text(raw["time_in_force"])

        return cls.model_validate(raw)


class Fill(BaseModel):
    """Fill record derived from broker trade updates."""

    order_id: str
    symbol: str
    side: str
    qty: Decimal
    price: Decimal | None = None
    filled_at: datetime | None = None

    model_config = ConfigDict(arbitrary_types_allowed=False)


class TrailingStopOrderRequest(BaseModel):
    """Broker-agnostic trailing stop order request."""

    symbol: str
    side: OrderSide
    qty: Decimal = Field(gt=0)
    trail_percent: Decimal = Field(gt=0)
    time_in_force: TimeInForce
    extended_hours: bool = False
    client_order_id: str | None = None

    model_config = ConfigDict(arbitrary_types_allowed=False)


def _normalize_enum_text(value: Any) -> str:
    if hasattr(value, "value"):
        return str(value.value).lower()
    text = str(value)
    if "." in text:
        text = text.split(".")[-1]
    return text.lower()


__all__ = ["Fill", "Order", "OrderSide", "TimeInForce", "TrailingStopOrderRequest"]
