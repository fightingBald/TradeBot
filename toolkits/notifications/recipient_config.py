"""Recipient configuration loader for email notifications."""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import List

from pydantic import BaseModel, EmailStr, Field


class RecipientConfig(BaseModel):
    """Typed configuration for notification recipients."""

    to: List[EmailStr] = Field(
        default_factory=list, description="Primary recipients (To)."
    )
    cc: List[EmailStr] = Field(
        default_factory=list, description="Carbon copy recipients (Cc)."
    )
    bcc: List[EmailStr] = Field(
        default_factory=list, description="Blind carbon copy recipients (Bcc)."
    )


def load_recipient_config(path: str | Path | None = None) -> RecipientConfig:
    """Load recipients from a TOML file.

    Args:
        path: Optional explicit path. If omitted, defaults to ``config/notification_recipients.toml``
              relative to项目根目录。

    Raises:
        FileNotFoundError: When the TOML file is missing。
        ValueError: When the file content无法解析.
    """

    if path is None:
        path = (
            Path(__file__).resolve().parents[1]
            / "config"
            / "notification_recipients.toml"
        )
    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(f"找不到收件人配置文件：{file_path}")
    try:
        data = tomllib.loads(file_path.read_text(encoding="utf-8"))
    except (
        tomllib.TOMLDecodeError
    ) as exc:  # pragma: no cover - unlikely when file is valid TOML
        raise ValueError(f"收件人配置解析失败：{file_path}") from exc
    return RecipientConfig.model_validate(data)


__all__ = ["RecipientConfig", "load_recipient_config"]
