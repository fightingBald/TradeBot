import inspect
from typing import Any, Dict, Iterable, List

from alpaca.common.exceptions import APIError
from alpaca.data import StockHistoricalDataClient
from alpaca.data.requests import StockLatestQuoteRequest
from alpaca.trading.client import TradingClient

from app.config import Settings
from app.models import UserPosition


class AlpacaMarketDataService:
    """Light wrapper around Alpaca's market data REST client."""

    def __init__(self, settings: Settings) -> None:
        client_kwargs = {
            "api_key": settings.api_key,
            "secret_key": settings.api_secret,
        }
        signature = inspect.signature(StockHistoricalDataClient.__init__)
        if "base_url" in signature.parameters:
            client_kwargs["base_url"] = settings.base_url
        self._client = StockHistoricalDataClient(**client_kwargs)
        self._data_feed = settings.data_feed

        trading_kwargs = {
            "api_key": settings.api_key,
            "secret_key": settings.api_secret,
            "paper": settings.paper_trading,
        }
        if settings.trading_base_url:
            trading_kwargs["base_url"] = settings.trading_base_url

        try:
            self._trading_client = TradingClient(**trading_kwargs)
        except TypeError:
            self._trading_client = TradingClient(
                settings.api_key,
                settings.api_secret,
                paper=settings.paper_trading,
            )

    def get_latest_quotes(self, symbols: Iterable[str]) -> Dict[str, Dict[str, Any]]:
        """Fetch latest quote for the provided ticker symbols."""
        symbols_list: List[str] = list({symbol.upper() for symbol in symbols})
        if not symbols_list:
            return {}

        request = StockLatestQuoteRequest(
            symbol_or_symbols=symbols_list,
            feed=self._data_feed,
        )

        try:
            response = self._client.get_stock_latest_quote(request)
        except APIError as exc:
            raise RuntimeError(f"Failed to fetch quotes from Alpaca: {exc}") from exc

        quotes: Dict[str, Dict[str, Any]] = {}
        for symbol in symbols_list:
            quote = response.get(symbol)
            if quote is None:
                continue
            quotes[symbol] = {
                "ask_price": quote.ask_price,
                "ask_size": quote.ask_size,
                "bid_price": quote.bid_price,
                "bid_size": quote.bid_size,
                "timestamp": quote.timestamp.isoformat() if quote.timestamp else None,
                "exchange": quote.exchange,
            }
        return quotes

    def get_user_positions(self) -> List[UserPosition]:
        """Fetch the currently open positions for the authenticated Alpaca account."""
        try:
            positions = self._trading_client.get_all_positions()
        except APIError as exc:
            raise RuntimeError(f"Failed to fetch positions from Alpaca: {exc}") from exc

        return [UserPosition.from_alpaca(position) for position in positions]
