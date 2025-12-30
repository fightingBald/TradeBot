from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import Annotated, Any

from fastapi import Depends, FastAPI, HTTPException, status
from pydantic import BaseModel, Field

from adapters.messaging.redis_command_bus import RedisCommandBus
from adapters.storage.sqlite_store import SqliteStateStore
from core.domain.commands import Command, CommandType
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


@asynccontextmanager
async def lifespan(app: FastAPI):
    _configure_logging()
    settings = Settings()
    state_store = SqliteStateStore(settings.database_url)
    command_bus = RedisCommandBus(settings.redis_url, settings.command_queue_name)

    app.state.settings = settings
    app.state.state_store = state_store
    app.state.command_bus = command_bus

    try:
        yield
    finally:
        state_store.close()
        await command_bus.close()


app = FastAPI(title="Trading Control API", version="0.2.0", lifespan=lifespan)


def get_settings() -> Settings:
    return app.state.settings


def get_state_store() -> SqliteStateStore:
    return app.state.state_store


def get_command_bus() -> RedisCommandBus:
    return app.state.command_bus


SettingsDep = Annotated[Settings, Depends(get_settings)]
StateStoreDep = Annotated[SqliteStateStore, Depends(get_state_store)]
CommandBusDep = Annotated[RedisCommandBus, Depends(get_command_bus)]


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
