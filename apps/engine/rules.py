from __future__ import annotations

import logging
from decimal import Decimal

from core.domain.order import TimeInForce

logger = logging.getLogger(__name__)



def coerce_tif_for_fractional(qty: Decimal, tif: TimeInForce, *, context: str) -> TimeInForce:
    if _is_fractional(qty) and tif is TimeInForce.GTC:
        logger.warning("Fractional qty requires DAY TIF; overriding (context=%s qty=%s)", context, qty)
        return TimeInForce.DAY
    return tif


def _is_fractional(qty: Decimal) -> bool:
    try:
        return qty % 1 != 0
    except Exception:
        return True
