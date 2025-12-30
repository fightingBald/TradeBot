from __future__ import annotations

import importlib
import sys
import types
import warnings
from enum import Enum
from pathlib import Path

# Ensure the application package is importable when running tests directly via pytest.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def _install_alpaca_stub() -> None:
    """Provide a minimal alpaca SDK shim for environments without alpaca-py."""

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", DeprecationWarning)
            importlib.import_module("alpaca.trading.enums")
        return
    except ModuleNotFoundError:
        pass

    alpaca_pkg = types.ModuleType("alpaca")
    trading_pkg = types.ModuleType("alpaca.trading")
    enums_pkg = types.ModuleType("alpaca.trading.enums")
    client_pkg = types.ModuleType("alpaca.trading.client")
    requests_pkg = types.ModuleType("alpaca.trading.requests")
    data_pkg = types.ModuleType("alpaca.data")
    data_requests_pkg = types.ModuleType("alpaca.data.requests")
    common_pkg = types.ModuleType("alpaca.common")
    exceptions_pkg = types.ModuleType("alpaca.common.exceptions")

    class OrderSide(str, Enum):
        BUY = "buy"
        SELL = "sell"

    class OrderType(str, Enum):
        STOP = "stop"
        MARKET = "market"

    class QueryOrderStatus(str, Enum):
        OPEN = "open"
        CLOSED = "closed"

    class TimeInForce(str, Enum):
        GTC = "gtc"

    class APIError(Exception):
        """Fallback Alpaca API error."""

    class TradingClient:  # pragma: no cover - only used when SDK missing
        def __init__(self, *_, **__) -> None:
            raise RuntimeError("alpaca-py is required for TradingClient usage.")

    class GetOrdersRequest:  # pragma: no cover - simple data holder
        def __init__(self, **kwargs) -> None:
            self.kwargs = kwargs

    class StopOrderRequest:
        def __init__(self, **kwargs) -> None:
            self.__dict__.update(kwargs)

    class StockHistoricalDataClient:
        def __init__(self, *_, **__) -> None:
            pass

        def get_stock_latest_quote(self, *_args, **_kwargs):
            raise RuntimeError("alpaca-py is required for market data operations.")

    class StockLatestQuoteRequest:
        def __init__(self, **kwargs) -> None:
            self.kwargs = kwargs

    enums_pkg.OrderSide = OrderSide
    enums_pkg.OrderType = OrderType
    enums_pkg.TimeInForce = TimeInForce
    enums_pkg.QueryOrderStatus = QueryOrderStatus

    client_pkg.TradingClient = TradingClient
    requests_pkg.GetOrdersRequest = GetOrdersRequest
    requests_pkg.StopOrderRequest = StopOrderRequest

    data_pkg.StockHistoricalDataClient = StockHistoricalDataClient
    data_requests_pkg.StockLatestQuoteRequest = StockLatestQuoteRequest

    exceptions_pkg.APIError = APIError

    # Wire up module hierarchy
    alpaca_pkg.trading = trading_pkg
    alpaca_pkg.data = data_pkg
    alpaca_pkg.common = common_pkg
    trading_pkg.enums = enums_pkg
    trading_pkg.client = client_pkg
    trading_pkg.requests = requests_pkg
    data_pkg.requests = data_requests_pkg
    common_pkg.exceptions = exceptions_pkg

    sys.modules["alpaca"] = alpaca_pkg
    sys.modules["alpaca.trading"] = trading_pkg
    sys.modules["alpaca.trading.enums"] = enums_pkg
    sys.modules["alpaca.trading.client"] = client_pkg
    sys.modules["alpaca.trading.requests"] = requests_pkg
    sys.modules["alpaca.data"] = data_pkg
    sys.modules["alpaca.data.requests"] = data_requests_pkg
    sys.modules["alpaca.common"] = common_pkg
    sys.modules["alpaca.common.exceptions"] = exceptions_pkg


_install_alpaca_stub()
