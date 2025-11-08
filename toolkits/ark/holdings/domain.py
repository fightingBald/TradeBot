"""Domain models for ARK ETF holdings."""

from __future__ import annotations

from datetime import date

from pydantic import BaseModel, Field


class Holding(BaseModel):
    """Single security holding within an ARK ETF snapshot."""

    as_of: date = Field(..., description="Snapshot date (trading day).")
    etf: str = Field(..., description="ETF symbol, e.g. ARKK.")
    company: str = Field(..., description="Company name as reported by ARK.")
    ticker: str = Field(..., description="Ticker symbol.")
    cusip: str | None = Field(default=None, description="CUSIP identifier when available.")
    shares: float | None = Field(default=None, description="Number of shares held.")
    market_value: float | None = Field(default=None, description="Market value in USD as reported by ARK.")
    weight: float | None = Field(default=None, description="Portfolio weight (0-1).")
    price: float | None = Field(default=None, description="Last price if provided.")


class HoldingSnapshot(BaseModel):
    """Collection of holdings for a single ETF on a given date."""

    etf: str = Field(..., description="ETF symbol.")
    as_of: date = Field(..., description="Snapshot date.")
    holdings: list[Holding] = Field(default_factory=list)

    def find(self, ticker: str) -> Holding | None:
        """Return holding for specific ticker if present."""
        for holding in self.holdings:
            if holding.ticker.upper() == ticker.upper():
                return holding
        return None

    @property
    def total_weight(self) -> float:
        """Total weight across holdings (should be close to 1)."""
        return sum(h.weight or 0.0 for h in self.holdings)

    @property
    def securities(self) -> list[str]:
        """List of tickers contained in snapshot."""
        return [h.ticker for h in self.holdings]
