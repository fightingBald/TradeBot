from functools import lru_cache

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings sourced from environment variables."""

    api_key: str = Field(
        validation_alias=AliasChoices("alpaca_api_key", "ALPACA_API_KEY", "apca_api_key_id", "APCA_API_KEY_ID")
    )
    api_secret: str = Field(
        validation_alias=AliasChoices(
            "alpaca_api_secret", "ALPACA_API_SECRET", "apca_api_secret_key", "APCA_API_SECRET_KEY"
        )
    )
    data_feed: str = Field(
        default="iex",
        validation_alias=AliasChoices("alpaca_data_feed", "ALPACA_DATA_FEED", "apca_data_feed", "APCA_DATA_FEED"),
    )
    base_url: str = Field(
        default="https://data.alpaca.markets/v2",
        validation_alias=AliasChoices(
            "alpaca_base_url",
            "ALPACA_BASE_URL",
            "apca_api_base_url",
            "APCA_API_BASE_URL",
            "apca_api_data_url",
            "APCA_API_DATA_URL",
        ),
    )
    trading_base_url: str = Field(
        default="https://paper-api.alpaca.markets",
        validation_alias=AliasChoices(
            "alpaca_trading_base_url",
            "ALPACA_TRADING_BASE_URL",
            "apca_api_trading_url",
            "APCA_API_TRADING_URL",
        ),
    )
    paper_trading: bool = Field(
        default=True,
        validation_alias=AliasChoices(
            "alpaca_paper_trading", "ALPACA_PAPER_TRADING", "apca_paper_trading", "APCA_PAPER_TRADING"
        ),
    )

    database_url: str = Field(
        default="sqlite:///./data/engine.db",
        validation_alias=AliasChoices("database_url", "DATABASE_URL", "db_url", "sqlite_url"),
    )
    redis_url: str = Field(
        default="redis://localhost:6379/0", validation_alias=AliasChoices("redis_url", "REDIS_URL")
    )
    command_queue_name: str = Field(
        default="alpaca:commands",
        validation_alias=AliasChoices(
            "command_queue_name", "COMMAND_QUEUE_NAME", "command_queue", "redis_command_queue"
        ),
    )
    engine_poll_interval_seconds: int = Field(
        default=10,
        validation_alias=AliasChoices("engine_poll_interval_seconds", "ENGINE_POLL_INTERVAL_SECONDS", "engine_poll_interval"),
    )
    engine_sync_min_interval_seconds: int = Field(
        default=3,
        validation_alias=AliasChoices(
            "engine_sync_min_interval_seconds",
            "ENGINE_SYNC_MIN_INTERVAL_SECONDS",
            "engine_sync_min_interval",
        ),
    )
    engine_profile_id: str = Field(
        default="default",
        validation_alias=AliasChoices("engine_profile_id", "ENGINE_PROFILE_ID", "profile_id"),
    )
    engine_enable_trading_ws: bool = Field(
        default=True,
        validation_alias=AliasChoices("engine_enable_trading_ws", "ENGINE_ENABLE_TRADING_WS", "engine_trading_ws"),
    )
    engine_trading_ws_max_backoff_seconds: int = Field(
        default=30,
        validation_alias=AliasChoices(
            "engine_trading_ws_max_backoff_seconds",
            "ENGINE_TRADING_WS_MAX_BACKOFF_SECONDS",
            "engine_trading_ws_backoff_max",
        ),
    )

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", env_prefix="", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    """Cached accessor so we only load settings once per process."""
    return Settings()
