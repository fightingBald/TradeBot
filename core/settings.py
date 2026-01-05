import logging
import os
from functools import lru_cache

from pydantic import AliasChoices, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)

DEFAULT_TRADING_BASE_URL_PAPER = "https://paper-api.alpaca.markets"
DEFAULT_TRADING_BASE_URL_LIVE = "https://api.alpaca.markets"

_KNOWN_ALPACA_ENV_KEYS = {
    "ALPACA_API_KEY",
    "ALPACA_API_KEY_ID",
    "ALPACA_API_SECRET",
    "ALPACA_API_SECRET_KEY",
    "ALPACA_DATA_FEED",
    "ALPACA_BASE_URL",
    "ALPACA_API_BASE_URL",
    "ALPACA_API_DATA_URL",
    "ALPACA_TRADING_BASE_URL",
    "ALPACA_API_TRADING_URL",
    "ALPACA_PAPER_TRADING",
}

_KNOWN_ENGINE_ENV_KEYS = {
    "ENGINE_POLL_INTERVAL_SECONDS",
    "ENGINE_SYNC_MIN_INTERVAL_SECONDS",
    "ENGINE_PROFILE_ID",
    "ENGINE_ENABLE_TRADING_WS",
    "ENGINE_TRADING_WS_MAX_BACKOFF_SECONDS",
    "ENGINE_TRAILING_DEFAULT_PERCENT",
    "ENGINE_TRAILING_BUY_TIF",
    "ENGINE_TRAILING_SELL_TIF",
    "ENGINE_AUTO_PROTECT_ENABLED",
    "ENGINE_AUTO_PROTECT_ORDER_TYPES",
}

_KNOWN_MARKETDATA_ENV_KEYS = {
    "MARKETDATA_STREAM_ENABLED",
    "MARKETDATA_SYMBOLS",
    "MARKETDATA_MAX_SYMBOLS",
    "MARKETDATA_SUBSCRIBE_QUOTES",
    "MARKETDATA_SUBSCRIBE_TRADES",
    "MARKETDATA_SUBSCRIBE_BARS",
    "MARKETDATA_BAR_TIMEFRAME",
    "MARKETDATA_BARS_MAX",
    "MARKETDATA_CACHE_TTL_SECONDS",
    "MARKETDATA_CACHE_NAMESPACE",
    "MARKETDATA_WS_URL",
    "MARKETDATA_WS_MAX_BACKOFF_SECONDS",
}


def _warn_unknown_prefixed_env(prefix: str, known_keys: set[str]) -> None:
    unknown = sorted(key for key in os.environ if key.startswith(prefix) and key not in known_keys)
    if unknown:
        logger.warning("Unknown %s env vars ignored: %s", prefix, ", ".join(unknown))


def _looks_like_trading_url(url: str) -> bool:
    return "paper-api.alpaca.markets" in url or (
        "api.alpaca.markets" in url and "data.alpaca.markets" not in url
    )


def _looks_like_data_url(url: str) -> bool:
    return "data.alpaca.markets" in url


class Settings(BaseSettings):
    """Application settings sourced from environment variables."""

    api_key: str = Field(
        validation_alias=AliasChoices("alpaca_api_key", "ALPACA_API_KEY", "alpaca_api_key_id", "ALPACA_API_KEY_ID")
    )
    api_secret: str = Field(
        validation_alias=AliasChoices(
            "alpaca_api_secret", "ALPACA_API_SECRET", "alpaca_api_secret_key", "ALPACA_API_SECRET_KEY"
        )
    )
    data_feed: str = Field(
        default="iex",
        validation_alias=AliasChoices("alpaca_data_feed", "ALPACA_DATA_FEED"),
    )
    base_url: str = Field(
        default="https://data.alpaca.markets/v2",
        validation_alias=AliasChoices(
            "alpaca_base_url",
            "ALPACA_BASE_URL",
            "alpaca_api_base_url",
            "ALPACA_API_BASE_URL",
            "alpaca_api_data_url",
            "ALPACA_API_DATA_URL",
        ),
    )
    trading_base_url: str = Field(
        default="https://paper-api.alpaca.markets",
        validation_alias=AliasChoices(
            "alpaca_trading_base_url",
            "ALPACA_TRADING_BASE_URL",
            "alpaca_api_trading_url",
            "ALPACA_API_TRADING_URL",
        ),
    )
    paper_trading: bool = Field(
        default=True,
        validation_alias=AliasChoices("alpaca_paper_trading", "ALPACA_PAPER_TRADING"),
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
        ge=1,
        validation_alias=AliasChoices(
            "engine_poll_interval_seconds", "ENGINE_POLL_INTERVAL_SECONDS", "engine_poll_interval"
        ),
    )
    engine_sync_min_interval_seconds: int = Field(
        default=3,
        ge=0,
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
        ge=1,
        validation_alias=AliasChoices(
            "engine_trading_ws_max_backoff_seconds",
            "ENGINE_TRADING_WS_MAX_BACKOFF_SECONDS",
            "engine_trading_ws_backoff_max",
        ),
    )
    engine_trailing_default_percent: float = Field(
        default=2.0,
        ge=0.01,
        validation_alias=AliasChoices(
            "engine_trailing_default_percent",
            "ENGINE_TRAILING_DEFAULT_PERCENT",
            "trailing_default_percent",
        ),
    )
    engine_trailing_buy_tif: str = Field(
        default="day",
        validation_alias=AliasChoices("engine_trailing_buy_tif", "ENGINE_TRAILING_BUY_TIF"),
    )
    engine_trailing_sell_tif: str = Field(
        default="gtc",
        validation_alias=AliasChoices("engine_trailing_sell_tif", "ENGINE_TRAILING_SELL_TIF"),
    )
    engine_auto_protect_enabled: bool = Field(
        default=True,
        validation_alias=AliasChoices("engine_auto_protect_enabled", "ENGINE_AUTO_PROTECT_ENABLED"),
    )
    engine_auto_protect_order_types: list[str] = Field(
        default_factory=lambda: ["market", "limit", "stop", "stop_limit", "trailing_stop"],
        validation_alias=AliasChoices("engine_auto_protect_order_types", "ENGINE_AUTO_PROTECT_ORDER_TYPES"),
    )

    marketdata_stream_enabled: bool = Field(
        default=True,
        validation_alias=AliasChoices("marketdata_stream_enabled", "MARKETDATA_STREAM_ENABLED"),
    )
    marketdata_symbols: list[str] = Field(
        default_factory=list,
        validation_alias=AliasChoices("marketdata_symbols", "MARKETDATA_SYMBOLS"),
    )
    marketdata_max_symbols: int = Field(
        default=30,
        ge=1,
        validation_alias=AliasChoices("marketdata_max_symbols", "MARKETDATA_MAX_SYMBOLS"),
    )
    marketdata_subscribe_quotes: bool = Field(
        default=True,
        validation_alias=AliasChoices("marketdata_subscribe_quotes", "MARKETDATA_SUBSCRIBE_QUOTES"),
    )
    marketdata_subscribe_trades: bool = Field(
        default=True,
        validation_alias=AliasChoices("marketdata_subscribe_trades", "MARKETDATA_SUBSCRIBE_TRADES"),
    )
    marketdata_subscribe_bars: bool = Field(
        default=True,
        validation_alias=AliasChoices("marketdata_subscribe_bars", "MARKETDATA_SUBSCRIBE_BARS"),
    )
    marketdata_bar_timeframe: str = Field(
        default="1Min",
        validation_alias=AliasChoices("marketdata_bar_timeframe", "MARKETDATA_BAR_TIMEFRAME"),
    )
    marketdata_bars_max: int = Field(
        default=120,
        ge=1,
        validation_alias=AliasChoices("marketdata_bars_max", "MARKETDATA_BARS_MAX"),
    )
    marketdata_cache_ttl_seconds: int = Field(
        default=30,
        ge=1,
        validation_alias=AliasChoices("marketdata_cache_ttl_seconds", "MARKETDATA_CACHE_TTL_SECONDS"),
    )
    marketdata_cache_namespace: str = Field(
        default="marketdata",
        validation_alias=AliasChoices("marketdata_cache_namespace", "MARKETDATA_CACHE_NAMESPACE"),
    )
    marketdata_ws_url: str = Field(
        default="",
        validation_alias=AliasChoices("marketdata_ws_url", "MARKETDATA_WS_URL"),
    )
    marketdata_ws_max_backoff_seconds: int = Field(
        default=30,
        ge=1,
        validation_alias=AliasChoices("marketdata_ws_max_backoff_seconds", "MARKETDATA_WS_MAX_BACKOFF_SECONDS"),
    )

    @field_validator("data_feed")
    @classmethod
    def _validate_data_feed(cls, value: str) -> str:
        feed = value.strip().lower()
        if feed not in {"iex", "sip"}:
            logger.warning("ALPACA_DATA_FEED=%s is unusual; expected 'iex' or 'sip'", value)
        return feed

    @field_validator("engine_trailing_buy_tif", "engine_trailing_sell_tif")
    @classmethod
    def _validate_trailing_tif(cls, value: str) -> str:
        tif = value.strip().lower()
        if tif not in {"day", "gtc"}:
            logger.warning("Trailing TIF=%s is unusual; expected 'day' or 'gtc'", value)
        return tif

    @field_validator("engine_auto_protect_order_types", mode="before")
    @classmethod
    def _parse_auto_protect_order_types(cls, value: object) -> list[str]:
        if isinstance(value, str):
            return [item.strip().lower() for item in value.split(",") if item.strip()]
        if isinstance(value, list):
            return [str(item).strip().lower() for item in value if str(item).strip()]
        return []

    @field_validator("marketdata_symbols", mode="before")
    @classmethod
    def _parse_marketdata_symbols(cls, value: object) -> list[str]:
        if isinstance(value, str):
            return [item.strip().upper() for item in value.split(",") if item.strip()]
        if isinstance(value, list):
            return [str(item).strip().upper() for item in value if str(item).strip()]
        return []

    @field_validator("marketdata_bar_timeframe", mode="before")
    @classmethod
    def _normalize_bar_timeframe(cls, value: str) -> str:
        return value.strip() if value else "1Min"

    @model_validator(mode="after")
    def _apply_defaults_and_warn(self) -> "Settings":
        if "trading_base_url" not in self.model_fields_set:
            self.trading_base_url = (
                DEFAULT_TRADING_BASE_URL_PAPER if self.paper_trading else DEFAULT_TRADING_BASE_URL_LIVE
            )

        if self.paper_trading and "paper-api.alpaca.markets" not in self.trading_base_url:
            logger.warning(
                "ALPACA_PAPER_TRADING=true but trading_base_url looks non-paper: %s", self.trading_base_url
            )
        if not self.paper_trading and "paper-api.alpaca.markets" in self.trading_base_url:
            logger.warning(
                "ALPACA_PAPER_TRADING=false but trading_base_url looks paper: %s", self.trading_base_url
            )
        if (
            "alpaca.markets" in self.base_url
            and not _looks_like_data_url(self.base_url)
            and _looks_like_trading_url(self.base_url)
        ):
            logger.warning("ALPACA_BASE_URL looks like trading endpoint: %s", self.base_url)

        _warn_unknown_prefixed_env("ALPACA_", _KNOWN_ALPACA_ENV_KEYS)
        _warn_unknown_prefixed_env("ENGINE_", _KNOWN_ENGINE_ENV_KEYS)
        _warn_unknown_prefixed_env("MARKETDATA_", _KNOWN_MARKETDATA_ENV_KEYS)

        if self.marketdata_stream_enabled and not self.marketdata_symbols:
            logger.warning("Market data stream enabled but MARKETDATA_SYMBOLS is empty")
        return self

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="",
        extra="ignore",
        enable_decoding=False,
    )


@lru_cache
def get_settings() -> Settings:
    """Cached accessor so we only load settings once per process."""
    return Settings()
