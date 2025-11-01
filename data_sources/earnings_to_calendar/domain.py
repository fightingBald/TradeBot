"""Domain entities and helpers for earnings calendar handling."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import List, Sequence, Tuple


@dataclass(frozen=True)
class EarningsEvent:
    """Normalized representation of a single earnings calendar event."""

    symbol: str
    date: date
    session: str = ""
    source: str = ""
    url: str | None = None
    notes: str | None = None

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
    """Parse the first 10 characters of the provided string into a date."""
    if not raw:
        return None
    text = raw.strip()
    if not text:
        return None
    candidate = text[:10]
    try:
        return date.fromisoformat(candidate)
    except ValueError:
        return None


def deduplicate_events(events: Sequence[EarningsEvent]) -> List[EarningsEvent]:
    """Remove duplicate events keeping the first occurrence for each (symbol, date)."""
    seen: set[Tuple[str, date]] = set()
    unique: List[EarningsEvent] = []
    for event in events:
        key = (event.symbol, event.date)
        if key in seen:
            continue
        seen.add(key)
        unique.append(event)
    return unique
