"""Apply stop-loss orders to all open Alpaca positions."""

from __future__ import annotations

import argparse
import logging
from collections.abc import Iterable
from decimal import ROUND_HALF_UP, Decimal

from alpaca.trading.client import TradingClient  # type: ignore  # noqa: E402
from alpaca.trading.enums import OrderSide, OrderType, QueryOrderStatus, TimeInForce  # type: ignore  # noqa: E402
from alpaca.trading.requests import GetOrdersRequest, StopOrderRequest  # type: ignore  # noqa: E402

from core.domain.position import Position  # noqa: E402
from core.settings import get_settings  # noqa: E402

STOP_ORDER_PREFIX = "STOPBOT-"

logger = logging.getLogger("alpaca.stop_loss")


def decimalize(value) -> Decimal:
    if value is None:
        return Decimal("0")
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def compute_stop_price(current_price: Decimal, stop_pct: Decimal) -> Decimal:
    price = decimalize(current_price)
    if price <= 0:
        raise ValueError("current_price must be positive")
    pct = decimalize(stop_pct)
    stop_price = price * (Decimal("1") - pct)
    if stop_price <= 0:
        raise ValueError("stop price computed as non-positive")
    return stop_price.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _is_long_position(position: Position) -> bool:
    return position.side.lower() == "long"


def _collect_managed_stop_orders(trading_client: TradingClient, symbols: Iterable[str]) -> dict[str, object]:
    request = GetOrdersRequest(status=QueryOrderStatus.OPEN, nested=True, symbols=list(set(symbols)))
    orders = trading_client.get_orders(request)
    managed = {}
    for order in orders:
        client_id = getattr(order, "client_order_id", "") or ""
        if not client_id.startswith(STOP_ORDER_PREFIX):
            continue
        if getattr(order, "order_type", None) != OrderType.STOP:
            continue
        managed[order.symbol] = order
    return managed


def apply_stop_losses(
    trading_client: TradingClient, *, stop_pct: Decimal, tolerance_pct: Decimal, dry_run: bool = False
) -> None:
    positions_raw = trading_client.get_all_positions()
    positions = [Position.from_alpaca(pos) for pos in positions_raw]
    symbols = [pos.symbol for pos in positions]
    managed_orders = _collect_managed_stop_orders(trading_client, symbols)

    logger.info("Found %d open positions, %d managed stop orders", len(positions), len(managed_orders))

    for position in positions:
        if not _is_long_position(position):
            logger.info("Skipping %s (side=%s)", position.symbol, position.side)
            continue

        current_price = position.current_price or position.lastday_price
        if current_price is None:
            logger.warning("Skipping %s (missing current price)", position.symbol)
            continue

        qty = decimalize(position.quantity)
        if qty <= 0:
            logger.info("Skipping %s (quantity=%s)", position.symbol, qty)
            continue

        try:
            stop_price = compute_stop_price(decimalize(current_price), stop_pct)
        except ValueError as exc:
            logger.warning("Skipping %s: %s", position.symbol, exc)
            continue

        existing_order = managed_orders.get(position.symbol)
        if existing_order is not None:
            existing_price = decimalize(getattr(existing_order, "stop_price", None))
            tolerance_value = stop_price * tolerance_pct
            if abs(existing_price - stop_price) <= tolerance_value:
                logger.info(
                    "Existing stop for %s within tolerance (%.2f vs %.2f) -> skip",
                    position.symbol,
                    existing_price,
                    stop_price,
                )
                continue
            if dry_run:
                logger.info("[dry-run] Would cancel order %s for %s", existing_order.id, position.symbol)
            else:
                trading_client.cancel_order_by_id(existing_order.id)
                logger.info("Cancelled order %s for %s", existing_order.id, position.symbol)

        if dry_run:
            logger.info("[dry-run] Would submit stop sell for %s qty=%s @ %.2f", position.symbol, qty, stop_price)
            continue

        order = StopOrderRequest(
            symbol=position.symbol,
            qty=float(qty),
            side=OrderSide.SELL,
            type=OrderType.STOP,
            time_in_force=TimeInForce.GTC,
            stop_price=float(stop_price),
            client_order_id=f"{STOP_ORDER_PREFIX}{position.symbol}",
        )
        trading_client.submit_order(order)
        logger.info("Submitted stop order for %s qty=%s @ %.2f", position.symbol, qty, stop_price)


def main() -> None:
    parser = argparse.ArgumentParser(description="Apply stop-loss orders to all Alpaca positions.")
    parser.add_argument(
        "--stop-pct",
        type=float,
        default=0.03,
        help="Percentage below current price to place stop (default: 0.03 = 3%%).",
    )
    parser.add_argument(
        "--tolerance-pct",
        type=float,
        default=0.005,
        help="Relative tolerance before replacing existing stop (default: 0.005 = 0.5%%).",
    )
    parser.add_argument("--dry-run", action="store_true", help="Log planned actions without submitting orders.")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s [set_stop_losses] %(message)s")
    settings = get_settings()
    trading_client = TradingClient(
        settings.api_key, settings.api_secret, paper=settings.paper_trading, base_url=settings.trading_base_url
    )
    apply_stop_losses(
        trading_client,
        stop_pct=Decimal(str(args.stop_pct)),
        tolerance_pct=Decimal(str(args.tolerance_pct)),
        dry_run=bool(args.dry_run),
    )


if __name__ == "__main__":
    main()
