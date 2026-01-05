from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


def _to_mapping(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if hasattr(value, "model_dump"):
        return value.model_dump()
    if hasattr(value, "dict"):
        return value.dict()
    if isinstance(value, dict):
        return value
    if hasattr(value, "__dict__"):
        return dict(value.__dict__)
    return {}


def _parse_timestamp(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str) and value:
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


class QuoteSnapshot(BaseModel):
    """Latest quote snapshot for a symbol."""

    symbol: str
    bid_price: Decimal | None = None
    bid_size: Decimal | None = None
    ask_price: Decimal | None = None
    ask_size: Decimal | None = None
    timestamp: datetime | None = None
    exchange: str | None = None

    model_config = ConfigDict(populate_by_name=True, arbitrary_types_allowed=False)

    @field_validator("symbol")
    @classmethod
    def _normalize_symbol(cls, value: str) -> str:
        return value.upper()

    @field_validator("timestamp", mode="before")
    @classmethod
    def _parse_timestamp_field(cls, value: Any) -> datetime | None:
        return _parse_timestamp(value)

    @classmethod
    def from_alpaca(cls, payload: Any) -> QuoteSnapshot:
        raw = _to_mapping(payload)
        return cls.model_validate(raw)


class TradeSnapshot(BaseModel):
    """Latest trade snapshot for a symbol."""

    symbol: str
    price: Decimal | None = None
    size: Decimal | None = None
    timestamp: datetime | None = None
    exchange: str | None = None
    conditions: list[str] | None = None
    trade_id: str | None = Field(default=None, validation_alias="id")

    model_config = ConfigDict(populate_by_name=True, arbitrary_types_allowed=False)

    @field_validator("symbol")
    @classmethod
    def _normalize_symbol(cls, value: str) -> str:
        return value.upper()

    @field_validator("timestamp", mode="before")
    @classmethod
    def _parse_timestamp_field(cls, value: Any) -> datetime | None:
        return _parse_timestamp(value)

    @classmethod
    def from_alpaca(cls, payload: Any) -> TradeSnapshot:
        raw = _to_mapping(payload)
        return cls.model_validate(raw)


class BarSnapshot(BaseModel):
    """Bar snapshot for a symbol/timeframe."""

    symbol: str
    timeframe: str = "1Min"
    timestamp: datetime | None = None
    open: Decimal | None = None
    high: Decimal | None = None
    low: Decimal | None = None
    close: Decimal | None = None
    volume: Decimal | None = None
    vwap: Decimal | None = None
    trade_count: int | None = None

    model_config = ConfigDict(populate_by_name=True, arbitrary_types_allowed=False)

    @field_validator("symbol")
    @classmethod
    def _normalize_symbol(cls, value: str) -> str:
        return value.upper()

    @field_validator("timestamp", mode="before")
    @classmethod
    def _parse_timestamp_field(cls, value: Any) -> datetime | None:
        return _parse_timestamp(value)

    @classmethod
    def from_alpaca(cls, payload: Any, *, timeframe: str = "1Min") -> BarSnapshot:
        raw = _to_mapping(payload)
        raw["timeframe"] = timeframe
        return cls.model_validate(raw)


__all__ = ["BarSnapshot", "QuoteSnapshot", "TradeSnapshot"]
