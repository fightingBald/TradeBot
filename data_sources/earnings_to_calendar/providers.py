"""Data providers that fetch earnings calendars from external APIs."""

from __future__ import annotations

from datetime import date
from typing import Callable, Dict, List, Sequence

import httpx
import numpy as np
import pandas as pd

from .logging_utils import get_logger
from .config import DEFAULT_TIMEOUT_SECONDS, USER_AGENT
from .domain import EarningsEvent

logger = get_logger()


class EarningsDataProvider:
    """Base class for earnings data providers."""

    source_name: str = ""

    def __init__(self, api_key: str | None) -> None:
        if not api_key:
            raise RuntimeError(f"{self.__class__.__name__}: API key required")
        self._api_key = api_key

    @staticmethod
    def _format_range(start: date, end: date) -> tuple[str, str]:
        return start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")

    def _get(self, url: str) -> httpx.Response:
        logger.debug("HTTP GET %s", url)
        response = httpx.get(url, headers={"User-Agent": USER_AGENT}, timeout=DEFAULT_TIMEOUT_SECONDS)
        response.raise_for_status()
        return response

    def fetch(
        self,
        symbols: Sequence[str],
        start: date,
        end: date,
    ) -> List[EarningsEvent]:
        raise NotImplementedError


class FmpEarningsProvider(EarningsDataProvider):
    source_name = "FMP"

    def fetch(
        self,
        symbols: Sequence[str],
        start: date,
        end: date,
    ) -> List[EarningsEvent]:
        since_s, until_s = self._format_range(start, end)
        url = (
            "https://financialmodelingprep.com/stable/earnings-calendar"
            f"?from={since_s}&to={until_s}&apikey={self._api_key}"
        )
        response = self._get(url)
        payload = response.json() or []
        if not payload:
            return []

        df = pd.DataFrame(payload)
        if df.empty or "symbol" not in df.columns:
            return []

        df["symbol"] = df["symbol"].astype(str).str.upper()
        watchlist = {symbol.upper() for symbol in symbols}
        df = df[df["symbol"].isin(watchlist)]
        if df.empty:
            return []

        date_values = df.get("date").fillna(df.get("earningsDate"))
        df["date"] = pd.to_datetime(date_values, errors="coerce").dt.date
        df = df.dropna(subset=["date"])
        if df.empty:
            return []

        if "time" in df.columns:
            df["session"] = df["time"].fillna("").astype(str).str.upper()
        else:
            df["session"] = np.repeat("", len(df))
        df["source"] = self.source_name

        events = [
            EarningsEvent(symbol=row.symbol, date=row.date, session=row.session, source=row.source)
            for row in df[["symbol", "date", "session", "source"]].itertuples(index=False)
        ]
        logger.info("FMP 返回 %d 条事件", len(events))
        return events


class FinnhubEarningsProvider(EarningsDataProvider):
    source_name = "Finnhub"

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
        response = self._get(url)
        payload = response.json() or {}
        data = payload.get("earningsCalendar", []) or []
        if not data:
            return []

        df = pd.DataFrame(data)
        if df.empty or "symbol" not in df.columns:
            return []

        df["symbol"] = df["symbol"].astype(str).str.upper()
        watchlist = {symbol.upper() for symbol in symbols}
        df = df[df["symbol"].isin(watchlist)]
        if df.empty:
            return []

        df["date"] = pd.to_datetime(df.get("date"), errors="coerce").dt.date
        df = df.dropna(subset=["date"])
        if df.empty:
            return []

        if "hour" in df.columns:
            df["session"] = df["hour"].fillna("").astype(str).str.upper()
        else:
            df["session"] = np.repeat("", len(df))
        df["source"] = self.source_name

        events = [
            EarningsEvent(symbol=row.symbol, date=row.date, session=row.session, source=row.source)
            for row in df[["symbol", "date", "session", "source"]].itertuples(index=False)
        ]
        logger.info("Finnhub 返回 %d 条事件", len(events))
        return events


PROVIDERS: Dict[str, Callable[[str | None], EarningsDataProvider]] = {
    "fmp": lambda api_key: FmpEarningsProvider(api_key),
    "finnhub": lambda api_key: FinnhubEarningsProvider(api_key),
}
