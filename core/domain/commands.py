from __future__ import annotations

from datetime import UTC, datetime
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


class CommandType(str, Enum):
    KILL_SWITCH = "kill_switch"
    DRAFT_ORDER = "draft_order"
    CONFIRM_ORDER = "confirm_order"


class Command(BaseModel):
    command_id: str = Field(default_factory=lambda: str(uuid4()))
    type: CommandType
    profile_id: str
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
