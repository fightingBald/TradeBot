from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import DateTime, Integer, Numeric, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class PositionRecord(Base):
    __tablename__ = "positions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    profile_id: Mapped[str] = mapped_column(String(64), index=True)
    symbol: Mapped[str] = mapped_column(String(64))
    asset_id: Mapped[str] = mapped_column(String(64))
    asset_class: Mapped[str | None] = mapped_column(String(32), nullable=True)
    exchange: Mapped[str | None] = mapped_column(String(32), nullable=True)
    side: Mapped[str] = mapped_column(String(16))
    quantity: Mapped[Decimal] = mapped_column(Numeric(20, 8))
    avg_entry_price: Mapped[Decimal] = mapped_column(Numeric(20, 8))
    market_value: Mapped[Decimal] = mapped_column(Numeric(20, 8))
    cost_basis: Mapped[Decimal] = mapped_column(Numeric(20, 8))
    unrealized_pl: Mapped[Decimal | None] = mapped_column(Numeric(20, 8), nullable=True)
    unrealized_plpc: Mapped[Decimal | None] = mapped_column(Numeric(20, 8), nullable=True)
    current_price: Mapped[Decimal | None] = mapped_column(Numeric(20, 8), nullable=True)
    lastday_price: Mapped[Decimal | None] = mapped_column(Numeric(20, 8), nullable=True)
    change_today: Mapped[Decimal | None] = mapped_column(Numeric(20, 8), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
