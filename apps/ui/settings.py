from __future__ import annotations

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class UiSettings(BaseSettings):
    """Settings for the Streamlit UI."""

    api_base_url: str = Field(
        default="http://localhost:8000", validation_alias=AliasChoices("api_base_url", "API_BASE_URL")
    )
    profile_id: str = Field(default="default", validation_alias=AliasChoices("profile_id", "PROFILE_ID"))
    marketdata_bars_limit: int = Field(
        default=120,
        ge=1,
        validation_alias=AliasChoices("marketdata_bars_limit", "MARKETDATA_BARS_MAX", "UI_MARKETDATA_BARS_LIMIT"),
    )
    marketdata_timeframe: str = Field(
        default="1Min",
        validation_alias=AliasChoices("marketdata_timeframe", "MARKETDATA_BAR_TIMEFRAME", "UI_MARKETDATA_TIMEFRAME"),
    )
    auto_refresh_seconds: int = Field(
        default=0,
        ge=0,
        validation_alias=AliasChoices("auto_refresh_seconds", "UI_AUTO_REFRESH_SECONDS"),
    )

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", env_prefix="", extra="ignore")
