from __future__ import annotations

import logging
from typing import Any

import httpx

from core.domain.market_data import BarSnapshot, QuoteSnapshot, TradeSnapshot
from core.domain.position import Position

logger = logging.getLogger(__name__)


class ApiError(RuntimeError):
    """Raised when the UI cannot reach the control API."""


def _request_json(
    method: str,
    url: str,
    *,
    params: dict[str, str] | None = None,
    payload: dict[str, Any] | None = None,
    timeout_seconds: int = 10,
) -> Any:
    try:
        response = httpx.request(method, url, params=params, json=payload, timeout=timeout_seconds)
        response.raise_for_status()
    except httpx.HTTPError as exc:
        logger.exception("API request failed: %s %s", method, url)
        raise ApiError(f"Failed to call API: {exc}") from exc
    return response.json()


def fetch_positions(api_base_url: str, profile_id: str) -> list[Position]:
    payload = _request_json(
        "GET",
        f"{api_base_url}/state/positions",
        params={"profile_id": profile_id},
    )
    return [Position.model_validate(item) for item in payload]


def fetch_profile(api_base_url: str, profile_id: str) -> dict[str, str]:
    return _request_json(
        "GET",
        f"{api_base_url}/state/profile",
        params={"profile_id": profile_id},
    )


def fetch_watchlist(api_base_url: str, profile_id: str) -> list[str]:
    payload = _request_json(
        "GET",
        f"{api_base_url}/market-data/watchlist",
        params={"profile_id": profile_id},
    )
    return [str(symbol).upper() for symbol in payload]


def fetch_quotes(api_base_url: str, profile_id: str, symbols: list[str]) -> dict[str, QuoteSnapshot]:
    payload = _request_json(
        "GET",
        f"{api_base_url}/market-data/quotes",
        params={"profile_id": profile_id, "symbols": ",".join(symbols)},
    )
    return {symbol: QuoteSnapshot.model_validate(data) for symbol, data in payload.items()}


def fetch_trades(api_base_url: str, profile_id: str, symbols: list[str]) -> dict[str, TradeSnapshot]:
    payload = _request_json(
        "GET",
        f"{api_base_url}/market-data/trades",
        params={"profile_id": profile_id, "symbols": ",".join(symbols)},
    )
    return {symbol: TradeSnapshot.model_validate(data) for symbol, data in payload.items()}


def fetch_bars(
    api_base_url: str,
    profile_id: str,
    symbols: list[str],
    *,
    limit: int,
    timeframe: str,
) -> dict[str, list[BarSnapshot]]:
    payload = _request_json(
        "GET",
        f"{api_base_url}/market-data/bars",
        params={
            "profile_id": profile_id,
            "symbols": ",".join(symbols),
            "limit": str(limit),
            "timeframe": timeframe,
        },
    )
    results: dict[str, list[BarSnapshot]] = {}
    for symbol, items in payload.items():
        results[symbol] = [BarSnapshot.model_validate(item) for item in items]
    return results


def request_kill_switch(
    api_base_url: str,
    *,
    profile_id: str,
    confirm_token: str,
    reason: str | None,
) -> dict[str, Any]:
    return _request_json(
        "POST",
        f"{api_base_url}/commands/kill-switch",
        payload={"profile_id": profile_id, "confirm_token": confirm_token, "reason": reason},
    )
