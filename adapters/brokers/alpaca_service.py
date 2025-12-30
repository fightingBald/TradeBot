import inspect
import logging
from collections.abc import Iterable
from typing import Any

from alpaca.common.exceptions import APIError
from alpaca.data import StockHistoricalDataClient
from alpaca.data.requests import StockLatestQuoteRequest
from alpaca.trading.client import TradingClient

from core.domain.position import Position
from core.settings import Settings

logger = logging.getLogger(__name__)


class AlpacaBrokerService:
    """Wrapper around Alpaca's trading + market data REST clients."""

    def __init__(self, settings: Settings) -> None:
        client_kwargs = {"api_key": settings.api_key, "secret_key": settings.api_secret}
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
            self._trading_client = TradingClient(settings.api_key, settings.api_secret, paper=settings.paper_trading)

    def get_latest_quotes(self, symbols: Iterable[str]) -> dict[str, dict[str, Any]]:
        """Fetch latest quote for the provided ticker symbols."""
        symbols_list: list[str] = list({symbol.upper() for symbol in symbols})
        if not symbols_list:
            return {}

        request = StockLatestQuoteRequest(symbol_or_symbols=symbols_list, feed=self._data_feed)

        try:
            response = self._client.get_stock_latest_quote(request)
        except APIError as exc:
            raise RuntimeError(f"Failed to fetch quotes from Alpaca: {exc}") from exc

        quotes: dict[str, dict[str, Any]] = {}
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

    def get_positions(self) -> list[Position]:
        """Fetch the currently open positions for the authenticated Alpaca account."""
        try:
            positions = self._trading_client.get_all_positions()
        except APIError as exc:
            raise RuntimeError(f"Failed to fetch positions from Alpaca: {exc}") from exc

        return [Position.from_alpaca(position) for position in positions]

    def cancel_open_orders(self) -> list[Any] | dict[str, Any]:
        """Cancel all open orders for the authenticated Alpaca account."""
        try:
            return self._trading_client.cancel_orders()
        except APIError as exc:
            logger.exception("Failed to cancel orders from Alpaca")
            raise RuntimeError(f"Failed to cancel orders from Alpaca: {exc}") from exc

    def close_all_positions(self, cancel_orders: bool | None = True) -> list[Any] | dict[str, Any]:
        """Close all open positions for the authenticated Alpaca account."""
        try:
            return self._trading_client.close_all_positions(cancel_orders=cancel_orders)
        except APIError as exc:
            logger.exception("Failed to close positions from Alpaca")
            raise RuntimeError(f"Failed to close positions from Alpaca: {exc}") from exc
