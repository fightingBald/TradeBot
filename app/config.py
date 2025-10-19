from functools import lru_cache

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings sourced from environment variables."""

    api_key: str = Field(validation_alias=AliasChoices("alpaca_api_key", "apca_api_key_id"))
    api_secret: str = Field(validation_alias=AliasChoices("alpaca_api_secret", "apca_api_secret_key"))
    data_feed: str = Field(default="iex", validation_alias=AliasChoices("alpaca_data_feed", "apca_data_feed"))
    base_url: str = Field(
        default="https://data.alpaca.markets/v2",
        validation_alias=AliasChoices("alpaca_base_url", "apca_api_base_url", "apca_api_data_url"),
    )
    trading_base_url: str = Field(
        default="https://paper-api.alpaca.markets",
        validation_alias=AliasChoices("alpaca_trading_base_url", "apca_api_trading_url"),
    )
    paper_trading: bool = Field(
        default=True,
        validation_alias=AliasChoices("alpaca_paper_trading", "apca_paper_trading"),
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    """Cached accessor so we only load settings once per process."""
    return Settings()
