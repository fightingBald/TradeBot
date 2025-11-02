from datetime import date

from data_sources.earnings_to_calendar.domain import EarningsEvent, deduplicate_events


def test_deduplicate_events_preserves_first_occurrence():
    first = EarningsEvent(symbol="AAPL", date=date(2024, 1, 10), session="BMO", source="FMP")
    duplicate = EarningsEvent(symbol="AAPL", date=date(2024, 1, 10), session="AMC", source="Finnhub")
    other = EarningsEvent(symbol="MSFT", date=date(2024, 1, 12), source="FMP")

    deduped = deduplicate_events([first, duplicate, other])

    assert deduped == [first, other]
