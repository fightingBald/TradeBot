from __future__ import annotations

from decimal import Decimal
from typing import Any

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator


class UserPosition(BaseModel):
    """Domain model representing an Alpaca trading position for a user."""

    symbol: str
    asset_id: str
    asset_class: str | None = None
    exchange: str | None = None
    side: str
    quantity: Decimal = Field(validation_alias=AliasChoices("quantity", "qty"))
    avg_entry_price: Decimal
    market_value: Decimal
    cost_basis: Decimal
    unrealized_pl: Decimal | None = None
    unrealized_plpc: Decimal | None = None
    current_price: Decimal | None = None
    lastday_price: Decimal | None = None
    change_today: Decimal | None = None

    model_config = ConfigDict(populate_by_name=True, arbitrary_types_allowed=False)

    @field_validator("asset_id", mode="before")
    @classmethod
    def ensure_asset_id_str(cls, value: Any) -> str:
        if value is None:
            raise ValueError("asset_id is required")
        return str(value)

    @classmethod
    def from_alpaca(cls, position: Any) -> UserPosition:
        """Factory that maps an Alpaca SDK Position object or dict into the domain model."""
        if hasattr(position, "model_dump"):
            raw: dict[str, Any] = position.model_dump()
        elif hasattr(position, "dict"):
            raw = position.dict()
        elif isinstance(position, dict):
            raw = position
        else:
            raise TypeError(f"Unsupported position type: {type(position)!r}")

        # Normalise quantity naming so external callers can keep using `qty`.
        if "quantity" not in raw and "qty" in raw:
            raw["quantity"] = raw.pop("qty")

        return cls.model_validate(raw)
