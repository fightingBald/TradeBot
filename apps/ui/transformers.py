from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal

import pandas as pd

from core.domain.position import Position


def _to_float(value: Decimal | None) -> float:
    if value is None:
        return float("nan")
    return float(value)


def positions_to_frame(positions: Sequence[Position]) -> pd.DataFrame:
    records: list[dict[str, object]] = []
    for position in positions:
        records.append(
            {
                "symbol": position.symbol,
                "side": position.side,
                "quantity": _to_float(position.quantity),
                "avg_entry_price": _to_float(position.avg_entry_price),
                "market_value": _to_float(position.market_value),
                "unrealized_pl": _to_float(position.unrealized_pl),
                "unrealized_plpc": _to_float(position.unrealized_plpc),
                "current_price": _to_float(position.current_price),
            }
        )

    df = pd.DataFrame.from_records(records)
    if df.empty:
        return df

    df["exposure_value"] = df["market_value"].abs()
    total_exposure = df["exposure_value"].sum()
    df["weight"] = df["exposure_value"] / total_exposure if total_exposure else 0.0
    df.sort_values("exposure_value", ascending=False, inplace=True)
    return df
