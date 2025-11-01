"""Data providers that fetch earnings calendars from external APIs."""

from __future__ import annotations

from datetime import date
from typing import Callable, Dict, List, Sequence

import requests

from .config import DEFAULT_TIMEOUT_SECONDS, USER_AGENT
from .domain import EarningsEvent, parse_iso_date


class EarningsDataProvider:
    """Base class for earnings data providers."""

    source_name: str = ""

    def __init__(self, http_get: Callable[..., requests.Response] | None = None) -> None:
        self._http_get = http_get or requests.get

    @staticmethod
    def _format_range(start: date, end: date) -> tuple[str, str]:
        return start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")

    def fetch(
        self,
        symbols: Sequence[str],
        start: date,
        end: date,
    ) -> List[EarningsEvent]:
        raise NotImplementedError


class FmpEarningsProvider(EarningsDataProvider):
    source_name = "FMP"

    def __init__(self, api_key: str | None, http_get: Callable[..., requests.Response] | None = None) -> None:
        if not api_key:
            raise RuntimeError("FMP_API_KEY 缺失")
        super().__init__(http_get=http_get)
        self._api_key = api_key

    def fetch(
        self,
        symbols: Sequence[str],
        start: date,
        end: date,
    ) -> List[EarningsEvent]:
        since_s, until_s = self._format_range(start, end)
        url = (
            "https://financialmodelingprep.com/api/v3/"
            f"earning_calendar?from={since_s}&to={until_s}&apikey={self._api_key}"
        )
        response = self._http_get(
            url,
            headers={"User-Agent": USER_AGENT},
            timeout=DEFAULT_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        payload = response.json() or []
        watchlist = {symbol.upper() for symbol in symbols}
        events: List[EarningsEvent] = []
        for item in payload:
            symbol = (item.get("symbol") or "").upper()
            if symbol not in watchlist:
                continue
            event_date = parse_iso_date(item.get("date") or item.get("earningsDate"))
            if event_date is None:
                continue
            session = (item.get("time") or "").upper()
            events.append(
                EarningsEvent(
                    symbol=symbol,
                    date=event_date,
                    session=session,
                    source=self.source_name,
                )
            )
        return events


class FinnhubEarningsProvider(EarningsDataProvider):
    source_name = "Finnhub"

    def __init__(self, api_key: str | None, http_get: Callable[..., requests.Response] | None = None) -> None:
        if not api_key:
            raise RuntimeError("FINNHUB_API_KEY 缺失")
        super().__init__(http_get=http_get)
        self._api_key = api_key

    def fetch(
        self,
        symbols: Sequence[str],
        start: date,
        end: date,
    ) -> List[EarningsEvent]:
        since_s, until_s = self._format_range(start, end)
        url = (
            "https://finnhub.io/api/v1/calendar/earnings"
            f"?from={since_s}&to={until_s}&token={self._api_key}"
        )
        response = self._http_get(
            url,
            headers={"User-Agent": USER_AGENT},
            timeout=DEFAULT_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        payload = response.json() or {}
        data = payload.get("earningsCalendar", []) or []
        watchlist = {symbol.upper() for symbol in symbols}
        events: List[EarningsEvent] = []
        for item in data:
            symbol = (item.get("symbol") or "").upper()
            if symbol not in watchlist:
                continue
            event_date = parse_iso_date(item.get("date"))
            if event_date is None:
                continue
            session = (item.get("hour") or "").upper()
            events.append(
                EarningsEvent(
                    symbol=symbol,
                    date=event_date,
                    session=session,
                    source=self.source_name,
                )
            )
        return events


PROVIDERS: Dict[str, Callable[[str | None], EarningsDataProvider]] = {
    "fmp": lambda api_key: FmpEarningsProvider(api_key),
    "finnhub": lambda api_key: FinnhubEarningsProvider(api_key),
}
