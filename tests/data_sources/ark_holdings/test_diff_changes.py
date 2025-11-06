from pathlib import Path

from src.ark.holdings import diff_snapshots
from src.ark.holdings.io import load_snapshot_csv


DATA_DIR = Path(__file__).parent / "data"


def test_diff_identifies_buys_sells_new_and_exits():
    old_snapshot = load_snapshot_csv(
        DATA_DIR / "ark_holdings_old" / "ARKK_2025-10-31.csv"
    )
    new_snapshot = load_snapshot_csv(
        DATA_DIR / "ark_holdings_new" / "ARKK_2025-10-31.csv"
    )

    changes = diff_snapshots(
        old_snapshot,
        new_snapshot,
        weight_threshold=0.0,
        share_threshold=0.0,
    )

    assert any(ch.ticker == "TSLA" and ch.action == "buy" for ch in changes)
    assert any(ch.ticker == "ROKU" and ch.action == "sell" for ch in changes)
    assert any(ch.ticker == "AIRO" and ch.action == "new" for ch in changes)
    assert any(ch.ticker == "SHOP" and ch.action == "exit" for ch in changes)
