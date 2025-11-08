"""Domain entities and helpers for earnings calendar handling."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date, datetime

from pydantic import BaseModel, Field, field_validator


class EarningsEvent(BaseModel):
    """Normalized representation of a single earnings calendar event."""

    symbol: str = Field(..., description="Ticker symbol")
    date: date
    session: str = Field("", description="BMO/AMC/UNSPECIFIED")
    source: str = Field("", description="Data provider name")
    url: str | None = None
    notes: str | None = None
    start_at: datetime | None = Field(default=None, description="Event start time (timezone-aware)")
    end_at: datetime | None = Field(default=None, description="Event end time (timezone-aware)")
    timezone: str | None = Field(default=None, description="Original timezone identifier")

    @field_validator("symbol", mode="before")
    @classmethod
    def _normalize_symbol(cls, value: str) -> str:
        return (value or "").strip().upper()

    @field_validator("session", mode="before")
    @classmethod
    def _normalize_session(cls, value: str) -> str:
        return (value or "").strip().upper()

    @field_validator("source", mode="before")
    @classmethod
    def _normalize_source(cls, value: str) -> str:
        return (value or "").strip()

    @property
    def iso_date(self) -> str:
        return self.date.strftime("%Y-%m-%d")

    def summary(self) -> str:
        if self.session:
            return f"{self.symbol} Earnings ({self.session})"
        return f"{self.symbol} Earnings"

    def description(self) -> str:
        base = f"Earnings date from {self.source or 'unknown'}"
        if self.notes:
            return f"{base}. {self.notes}"
        return f"{base}."


def parse_iso_date(raw: str | None) -> date | None:
    """Parse a string into date if possible."""
    if not raw:
        return None
    text = raw.strip()
    if not text:
        return None
    candidate = text[:10]
    try:
        return date.fromisoformat(candidate)
    except ValueError:  # pragma: no cover - guarded parser
        return None


def deduplicate_events(events: Sequence[EarningsEvent]) -> list[EarningsEvent]:
    """Remove duplicate events keeping the first occurrence for each (symbol, date)."""
    seen: set[tuple[str, date]] = set()
    unique: list[EarningsEvent] = []
    for event in events:
        key = (event.symbol, event.date)
        if key in seen:
            continue
        seen.add(key)
        unique.append(event)
    return unique


def earnings_key(event: EarningsEvent) -> str:
    """Stable identifier used for calendar sync."""
    session = (event.session or "").upper() or "UNSPECIFIED"
    return f"{event.symbol.upper()}::{event.iso_date}::{session}"


__all__ = ["EarningsEvent", "parse_iso_date", "deduplicate_events", "earnings_key"]
