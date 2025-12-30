"""Data providers that fetch earnings calendars from external APIs."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

import httpx
import numpy as np
import pandas as pd

from .defaults import DEFAULT_EVENT_DURATION_MINUTES, DEFAULT_SESSION_TIMES, DEFAULT_TIMEOUT_SECONDS, USER_AGENT
from .domain import EarningsEvent
from .logging_utils import get_logger

logger = get_logger()


class EarningsDataProvider:
    """Base class for earnings data providers."""

    source_name: str = ""

    def __init__(
        self,
        api_key: str | None,
        *,
        source_timezone: str,
        session_times: dict[str, str] | None = None,
        event_duration_minutes: int = DEFAULT_EVENT_DURATION_MINUTES,
    ) -> None:
        if not api_key:
            raise RuntimeError(f"{self.__class__.__name__}: API key required")
        self._api_key = api_key
        self._source_tz = ZoneInfo(source_timezone)
        mapping = session_times or DEFAULT_SESSION_TIMES
        self._session_times = {str(k).upper(): str(v) for k, v in mapping.items()}
        self._event_duration = timedelta(minutes=max(event_duration_minutes, 1))

    @staticmethod
    def _format_range(start: date, end: date) -> tuple[str, str]:
        return start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d")

    def _get(self, url: str) -> httpx.Response:
        logger.debug("HTTP GET %s", url)
        response = httpx.get(url, headers={"User-Agent": USER_AGENT}, timeout=DEFAULT_TIMEOUT_SECONDS)
        response.raise_for_status()
        return response

    @staticmethod
    def _parse_time_string(value: str | None) -> time | None:
        if not value:
            return None
        if isinstance(value, float | np.floating) and np.isnan(value):
            return None
        text = str(value).strip()
        if not text:
            return None
        formats = ["%H:%M", "%H:%M:%S", "%I:%M %p", "%I %p"]
        for fmt in formats:
            try:
                return datetime.strptime(text, fmt).time()  # noqa: DTZ007
            except ValueError:
                continue
        return None

    def _build_datetime(
        self, event_date: date, session: str, raw_time: str | None
    ) -> tuple[datetime | None, datetime | None]:
        time_obj = self._parse_time_string(raw_time)
        if time_obj is None:
            mapped = self._session_times.get(session.upper())
            time_obj = self._parse_time_string(mapped)
        if time_obj is None:
            return None, None
        start = datetime.combine(event_date, time_obj, tzinfo=self._source_tz)
        end = start + self._event_duration
        return start, end

    def fetch(self, symbols: Sequence[str], start: date, end: date) -> list[EarningsEvent]:
        raise NotImplementedError


class FmpEarningsProvider(EarningsDataProvider):
    source_name = "FMP"

    def __init__(self, api_key: str | None, **kwargs) -> None:
        super().__init__(api_key, **kwargs)

    def fetch(self, symbols: Sequence[str], start: date, end: date) -> list[EarningsEvent]:
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

        date_col = df.get("date")
        data = date_col if date_col is not None else pd.Series([None] * len(df))
        fallback = df["earningsDate"] if "earningsDate" in df.columns else pd.Series([None] * len(df))
        date_values = data.where(data.notna(), fallback)
        df["date"] = pd.to_datetime(date_values, errors="coerce").dt.date
        df = df.dropna(subset=["date"])
        if df.empty:
            return []

        if "time" in df.columns:
            df["session"] = df["time"].fillna("").astype(str).str.upper()
        else:
            df["session"] = np.repeat("", len(df))
        df["time"] = df.get("time")
        df["source"] = self.source_name

        events: list[EarningsEvent] = []
        for row in df[["symbol", "date", "session", "source", "time"]].itertuples(index=False, name="Row"):
            start_at, end_at = self._build_datetime(row.date, row.session, getattr(row, "time", None))
            events.append(
                EarningsEvent(
                    symbol=row.symbol,
                    date=row.date,
                    session=row.session,
                    source=row.source,
                    start_at=start_at,
                    end_at=end_at,
                    timezone=self._source_tz.key,
                )
            )
        logger.info("FMP 返回 %d 条事件", len(events))
        return events


class FinnhubEarningsProvider(EarningsDataProvider):
    source_name = "Finnhub"

    def __init__(self, api_key: str | None, **kwargs) -> None:
        super().__init__(api_key, **kwargs)

    def fetch(self, symbols: Sequence[str], start: date, end: date) -> list[EarningsEvent]:
        since_s, until_s = self._format_range(start, end)
        url = "https://finnhub.io/api/v1/calendar/earnings" f"?from={since_s}&to={until_s}&token={self._api_key}"
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
        df["hour"] = df.get("hour")
        df["source"] = self.source_name

        events: list[EarningsEvent] = []
        for row in df[["symbol", "date", "session", "source", "hour"]].itertuples(index=False, name="Row"):
            start_at, end_at = self._build_datetime(row.date, row.session, getattr(row, "hour", None))
            events.append(
                EarningsEvent(
                    symbol=row.symbol,
                    date=row.date,
                    session=row.session,
                    source=row.source,
                    start_at=start_at,
                    end_at=end_at,
                    timezone=self._source_tz.key,
                )
            )
        logger.info("Finnhub 返回 %d 条事件", len(events))
        return events


PROVIDERS: dict[str, Callable[..., EarningsDataProvider]] = {
    "fmp": FmpEarningsProvider,
    "finnhub": FinnhubEarningsProvider,
}
