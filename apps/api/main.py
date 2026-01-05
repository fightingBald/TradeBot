from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Annotated, Any

from fastapi import Depends, FastAPI, HTTPException, status
from pydantic import BaseModel, Field

from adapters.market_data.redis_cache import RedisMarketDataCache
from adapters.messaging.redis_command_bus import RedisCommandBus
from adapters.storage.sqlalchemy_state_store import SqlAlchemyStateStore
from core.domain.commands import Command, CommandType
from core.domain.market_data import BarSnapshot, QuoteSnapshot, TradeSnapshot
from core.domain.position import Position
from core.settings import Settings

logger = logging.getLogger(__name__)


def _configure_logging() -> None:
    root_logger = logging.getLogger()
    if root_logger.handlers:
        return
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


class KillSwitchRequest(BaseModel):
    profile_id: str = Field(default="default")
    confirm_token: str
    reason: str | None = None


class DraftOrderRequest(BaseModel):
    profile_id: str = Field(default="default")
    symbol: str
    side: str
    qty: float
    order_type: str = Field(default="stop")
    stop_price: float | None = None


class ConfirmOrderRequest(BaseModel):
    profile_id: str = Field(default="default")
    draft_id: str


class TrailingStopBuyRequest(BaseModel):
    profile_id: str = Field(default="default")
    symbol: str
    qty: float = Field(gt=0)
    trail_percent: float | None = Field(default=None, gt=0)
    client_order_id: str | None = None


class TrailingStopLossRequest(BaseModel):
    profile_id: str = Field(default="default")
    symbol: str
    qty: float | None = Field(default=None, gt=0)
    trail_percent: float | None = Field(default=None, gt=0)
    client_order_id: str | None = None


class MarketDataQuery(BaseModel):
    profile_id: str | None = None
    symbols: str | None = None
    limit: int | None = None
    timeframe: str | None = None


MarketDataQueryDep = Depends(MarketDataQuery)


@asynccontextmanager
async def lifespan(app: FastAPI):
    _configure_logging()
    settings = Settings()
    state_store = SqlAlchemyStateStore(settings.database_url)
    command_bus = RedisCommandBus(settings.redis_url, settings.command_queue_name)
    market_cache = RedisMarketDataCache(
        settings.redis_url,
        namespace=settings.marketdata_cache_namespace,
        ttl_seconds=settings.marketdata_cache_ttl_seconds,
    )

    app.state.settings = settings
    app.state.state_store = state_store
    app.state.command_bus = command_bus
    app.state.market_cache = market_cache

    try:
        yield
    finally:
        state_store.close()
        await command_bus.close()
        await market_cache.close()


app = FastAPI(title="Trading Control API", version="0.2.0", lifespan=lifespan)


def get_settings() -> Settings:
    return app.state.settings


def get_state_store() -> SqlAlchemyStateStore:
    return app.state.state_store


def get_command_bus() -> RedisCommandBus:
    return app.state.command_bus


def get_market_cache() -> RedisMarketDataCache:
    return app.state.market_cache


SettingsDep = Annotated[Settings, Depends(get_settings)]
StateStoreDep = Annotated[SqlAlchemyStateStore, Depends(get_state_store)]
CommandBusDep = Annotated[RedisCommandBus, Depends(get_command_bus)]
MarketCacheDep = Annotated[RedisMarketDataCache, Depends(get_market_cache)]


def _parse_symbols(raw: str | None) -> list[str]:
    if not raw:
        return []
    return [item.strip().upper() for item in raw.split(",") if item.strip()]


@app.get("/health", summary="Health check", status_code=status.HTTP_200_OK)
async def healthcheck() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/state/profile", summary="Current profile", status_code=status.HTTP_200_OK)
async def read_profile(settings: SettingsDep) -> dict[str, str]:
    environment = "paper" if settings.paper_trading else "live"
    return {"profile_id": settings.engine_profile_id, "environment": environment}


@app.get("/state/positions", summary="Current positions", status_code=status.HTTP_200_OK)
async def read_positions(
    store: StateStoreDep,
    settings: SettingsDep,
    profile_id: str | None = None,
) -> list[Position]:
    effective_profile = profile_id or settings.engine_profile_id
    return store.list_positions(effective_profile)


@app.get("/market-data/watchlist", summary="Market data watchlist", status_code=status.HTTP_200_OK)
async def read_watchlist(
    cache: MarketCacheDep,
    settings: SettingsDep,
    profile_id: str | None = None,
) -> list[str]:
    effective_profile = profile_id or settings.engine_profile_id
    watchlist = await cache.get_watchlist(effective_profile)
    if not watchlist:
        watchlist = settings.marketdata_symbols
    return watchlist


@app.get("/market-data/quotes", summary="Latest quotes", status_code=status.HTTP_200_OK)
async def read_quotes(
    cache: MarketCacheDep,
    settings: SettingsDep,
    query: MarketDataQuery = MarketDataQueryDep,
) -> dict[str, QuoteSnapshot]:
    effective_profile = query.profile_id or settings.engine_profile_id
    parsed_symbols = _parse_symbols(query.symbols)
    if not parsed_symbols:
        parsed_symbols = await cache.get_watchlist(effective_profile) or settings.marketdata_symbols
    return await cache.get_latest_quotes(effective_profile, parsed_symbols)


@app.get("/market-data/trades", summary="Latest trades", status_code=status.HTTP_200_OK)
async def read_trades(
    cache: MarketCacheDep,
    settings: SettingsDep,
    query: MarketDataQuery = MarketDataQueryDep,
) -> dict[str, TradeSnapshot]:
    effective_profile = query.profile_id or settings.engine_profile_id
    parsed_symbols = _parse_symbols(query.symbols)
    if not parsed_symbols:
        parsed_symbols = await cache.get_watchlist(effective_profile) or settings.marketdata_symbols
    return await cache.get_latest_trades(effective_profile, parsed_symbols)


@app.get("/market-data/bars", summary="Recent bars", status_code=status.HTTP_200_OK)
async def read_bars(
    cache: MarketCacheDep,
    settings: SettingsDep,
    query: MarketDataQuery = MarketDataQueryDep,
) -> dict[str, list[BarSnapshot]]:
    effective_profile = query.profile_id or settings.engine_profile_id
    parsed_symbols = _parse_symbols(query.symbols)
    if not parsed_symbols:
        parsed_symbols = await cache.get_watchlist(effective_profile) or settings.marketdata_symbols
    effective_limit = query.limit or settings.marketdata_bars_max
    effective_timeframe = query.timeframe or settings.marketdata_bar_timeframe
    return await cache.get_recent_bars(
        effective_profile, parsed_symbols, limit=effective_limit, timeframe=effective_timeframe
    )


@app.post("/commands/kill-switch", summary="Request kill switch", status_code=status.HTTP_202_ACCEPTED)
async def kill_switch(
    request: KillSwitchRequest,
    settings: SettingsDep,
    bus: CommandBusDep,
) -> dict[str, Any]:
    expected = "LIVE" if not settings.paper_trading else "PAPER"
    if request.confirm_token.upper() != expected:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid confirmation token")

    command = Command(
        type=CommandType.KILL_SWITCH,
        profile_id=request.profile_id,
        payload={"reason": request.reason, "requested_by": "ui"},
    )
    await bus.publish(command)
    logger.warning("Kill switch queued command_id=%s profile=%s", command.command_id, request.profile_id)
    return {"command_id": command.command_id}


@app.post("/commands/draft", summary="Draft order", status_code=status.HTTP_202_ACCEPTED)
async def draft_order(
    request: DraftOrderRequest,
    bus: CommandBusDep,
) -> dict[str, Any]:
    command = Command(
        type=CommandType.DRAFT_ORDER,
        profile_id=request.profile_id,
        payload=request.model_dump(),
    )
    await bus.publish(command)
    return {"command_id": command.command_id}


@app.post("/commands/confirm", summary="Confirm order", status_code=status.HTTP_202_ACCEPTED)
async def confirm_order(
    request: ConfirmOrderRequest,
    bus: CommandBusDep,
) -> dict[str, Any]:
    command = Command(
        type=CommandType.CONFIRM_ORDER,
        profile_id=request.profile_id,
        payload=request.model_dump(),
    )
    await bus.publish(command)
    return {"command_id": command.command_id}


@app.post("/commands/trailing-stop-buy", summary="Trailing stop buy", status_code=status.HTTP_202_ACCEPTED)
async def trailing_stop_buy(
    request: TrailingStopBuyRequest,
    bus: CommandBusDep,
) -> dict[str, Any]:
    command = Command(
        type=CommandType.TRAILING_STOP_BUY,
        profile_id=request.profile_id,
        payload=request.model_dump(),
    )
    await bus.publish(command)
    return {"command_id": command.command_id}


@app.post("/commands/trailing-stop-loss", summary="Trailing stop loss", status_code=status.HTTP_202_ACCEPTED)
async def trailing_stop_loss(
    request: TrailingStopLossRequest,
    bus: CommandBusDep,
) -> dict[str, Any]:
    command = Command(
        type=CommandType.TRAILING_STOP_SELL,
        profile_id=request.profile_id,
        payload=request.model_dump(),
    )
    await bus.publish(command)
    return {"command_id": command.command_id}
