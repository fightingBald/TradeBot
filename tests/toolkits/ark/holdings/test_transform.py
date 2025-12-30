import io

import pandas as pd
import pytest

from toolkits.ark.holdings.transform import parse_snapshot


def test_parse_snapshot_normalizes_columns_and_values():
    csv = """date,fund,company,ticker,cusip,shares,market value ($),weight (%)
10/31/2025,ARKK,TESLA INC,TSLA,88160R101,2263127,"$996,002,192.70","12.30%"
"""
    df = pd.read_csv(io.StringIO(csv))
    as_of, cleaned = parse_snapshot(df)
    assert as_of.strftime("%Y-%m-%d") == "2025-10-31"
    row = cleaned.iloc[0]
    assert row["ticker"] == "TSLA"
    assert row["shares"] == 2263127.0
    assert pytest.approx(row["market_value"], rel=1e-6) == 996002192.70
    assert pytest.approx(row["weight"], rel=1e-6) == 0.123
