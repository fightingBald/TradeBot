from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from app.config import Settings, get_settings
from app.models import UserPosition
from app.services.alpaca_market_data import AlpacaMarketDataService

app = FastAPI(title="Alpaca Market Data API", version="0.1.0")

templates = Jinja2Templates(directory="app/templates")
DEFAULT_SYMBOLS = ["AAPL", "GOOGL"]


SettingsDep = Annotated[Settings, Depends(get_settings)]


def get_market_data_service(settings: SettingsDep) -> AlpacaMarketDataService:
    """Dependency provider for the Alpaca market data service."""
    return AlpacaMarketDataService(settings)


MarketDataServiceDep = Annotated[AlpacaMarketDataService, Depends(get_market_data_service)]


@app.get("/", response_class=HTMLResponse)
async def index(
    request: Request,
    symbols: Annotated[
        list[str] | None, Query(default=None, description="Optional symbols to chart on the heatmap")
    ] = None,
) -> HTMLResponse:
    tickers = symbols or DEFAULT_SYMBOLS
    return templates.TemplateResponse(
        "index.html", {"request": request, "symbols": tickers, "poll_interval_seconds": 5}
    )


@app.get("/quotes", summary="Latest quotes", status_code=status.HTTP_200_OK)
async def read_quotes(
    service: MarketDataServiceDep,
    symbols: Annotated[
        list[str] | None, Query(default=None, description="Ticker symbols to fetch (defaults to AAPL and GOOGL)")
    ] = None,
) -> dict:
    tickers = symbols or DEFAULT_SYMBOLS

    try:
        quotes = service.get_latest_quotes(tickers)
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    if not quotes:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="No quote data returned for requested symbols."
        )

    return {"quotes": quotes}


@app.get("/positions", summary="Current positions", status_code=status.HTTP_200_OK, response_model=list[UserPosition])
async def read_positions(service: MarketDataServiceDep) -> list[UserPosition]:
    try:
        positions = service.get_user_positions()
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)) from exc

    return positions


@app.get("/health", summary="Health check", status_code=status.HTTP_200_OK)
async def healthcheck() -> dict:
    return {"status": "ok"}
