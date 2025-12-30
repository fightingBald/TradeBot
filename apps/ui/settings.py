from __future__ import annotations

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class UiSettings(BaseSettings):
    """Settings for the Streamlit UI."""

    api_base_url: str = Field(
        default="http://localhost:8000", validation_alias=AliasChoices("api_base_url", "API_BASE_URL")
    )
    profile_id: str = Field(default="default", validation_alias=AliasChoices("profile_id", "PROFILE_ID"))

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", env_prefix="", extra="ignore")
