"""Local sync state helpers to support incremental calendar updates."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Mapping

from .domain import EarningsEvent, earnings_key
from .logging_utils import get_logger

logger = get_logger()


@dataclass
class SyncEntry:
    hash: str
    updated_at: str


@dataclass
class SyncState:
    events: Dict[str, SyncEntry] = field(default_factory=dict)
    time_window: Mapping[str, str] | None = None


@dataclass
class SyncDiff:
    to_create: List[EarningsEvent] = field(default_factory=list)
    to_update: List[EarningsEvent] = field(default_factory=list)
    unchanged: List[EarningsEvent] = field(default_factory=list)
    removed_keys: List[str] = field(default_factory=list)
    fingerprints: Dict[str, str] = field(default_factory=dict)


def _serialize_event(event: EarningsEvent) -> Dict[str, object]:
    return {
        "symbol": event.symbol,
        "date": event.iso_date,
        "session": event.session,
        "source": event.source,
        "url": event.url,
        "notes": event.notes,
        "start_at": event.start_at.isoformat() if event.start_at else None,
        "end_at": event.end_at.isoformat() if event.end_at else None,
        "timezone": event.timezone,
    }


def _fingerprint_event(event: EarningsEvent) -> str:
    payload = _serialize_event(event)
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def diff_events(events: Iterable[EarningsEvent], state: SyncState | None) -> SyncDiff:
    state_map = state.events if state else {}
    diff = SyncDiff()
    for event in events:
        key = earnings_key(event)
        fingerprint = _fingerprint_event(event)
        diff.fingerprints[key] = fingerprint
        entry = state_map.get(key)
        if entry is None:
            diff.to_create.append(event)
        elif entry.hash != fingerprint:
            diff.to_update.append(event)
        else:
            diff.unchanged.append(event)
    diff.removed_keys = [key for key in state_map if key not in diff.fingerprints]
    return diff


def load_sync_state(path: str | None) -> SyncState:
    if not path:
        return SyncState()
    file_path = Path(path)
    if not file_path.exists():
        return SyncState()
    try:
        with file_path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("读取增量同步状态失败，将忽略并重新生成：%s", exc)
        return SyncState()
    events_payload = payload.get("events", {}) if isinstance(payload, dict) else {}
    events: Dict[str, SyncEntry] = {}
    if isinstance(events_payload, dict):
        for key, entry in events_payload.items():
            if not isinstance(entry, dict):
                continue
            hash_value = entry.get("hash")
            if not hash_value:
                continue
            updated_at = entry.get("updated_at", "")
            events[key] = SyncEntry(hash=str(hash_value), updated_at=str(updated_at))
    window = payload.get("time_window") if isinstance(payload, dict) else None
    return SyncState(events=events, time_window=window)


def _now_iso_utc() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def build_sync_state(
    events: Iterable[EarningsEvent],
    fingerprints: Mapping[str, str],
    *,
    since: date,
    until: date,
) -> SyncState:
    timestamp = _now_iso_utc()
    entries: Dict[str, SyncEntry] = {}
    for event in events:
        key = earnings_key(event)
        fingerprint = fingerprints.get(key)
        if fingerprint is None:
            fingerprint = _fingerprint_event(event)
        entries[key] = SyncEntry(hash=fingerprint, updated_at=timestamp)
    window = {"since": since.isoformat(), "until": until.isoformat()}
    return SyncState(events=entries, time_window=window)


def save_sync_state(path: str, state: SyncState) -> None:
    file_path = Path(path)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "time_window": state.time_window,
        "events": {
            key: {"hash": entry.hash, "updated_at": entry.updated_at}
            for key, entry in state.events.items()
        },
    }
    with file_path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)


__all__ = [
    "SyncDiff",
    "SyncEntry",
    "SyncState",
    "build_sync_state",
    "diff_events",
    "load_sync_state",
    "save_sync_state",
]
