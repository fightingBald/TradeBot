from __future__ import annotations

import logging
from typing import Any

import httpx

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
