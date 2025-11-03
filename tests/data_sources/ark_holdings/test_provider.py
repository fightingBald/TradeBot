from datetime import date

import pytest

from data_sources.ark_holdings import fetch_holdings_snapshot


class DummyResponse:
    def __init__(self, text: str):
        self.text = text

    def raise_for_status(self):
        return None


def test_fetch_holdings_snapshot(monkeypatch):
    csv = """date,fund,company,ticker,cusip,shares,market value ($),weight (%)
10/31/2025,ARKK,TESLA INC,TSLA,88160R101,2263127,"$996,002,192.70","12.30%"
"""

    def fake_get(url, timeout, headers):  # noqa: ANN001
        return DummyResponse(csv)

    monkeypatch.setattr("data_sources.ark_holdings.provider.requests.get", fake_get)

    snapshot = fetch_holdings_snapshot("ARKK")
    assert snapshot.etf == "ARKK"
    assert snapshot.as_of == date(2025, 10, 31)
    assert len(snapshot.holdings) == 1
    holding = snapshot.holdings[0]
    assert holding.ticker == "TSLA"
    assert holding.shares == 2263127.0
    assert pytest.approx(holding.weight, rel=1e-6) == 0.123
