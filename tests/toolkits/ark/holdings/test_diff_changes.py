from pathlib import Path

from toolkits.ark.holdings import diff_snapshots
from toolkits.ark.holdings.io import load_snapshot_csv

DATA_DIR = Path(__file__).parent / "data"


def test_diff_identifies_buys_sells_new_and_exits():
    old_snapshot = load_snapshot_csv(DATA_DIR / "ark_holdings_old" / "ARKW_2025-10-31.csv")
    new_snapshot = load_snapshot_csv(DATA_DIR / "ark_holdings_new" / "ARKW_2025-10-31.csv")

    changes = diff_snapshots(old_snapshot, new_snapshot, weight_threshold=0.0, share_threshold=0.0)

    assert any(ch.ticker == "TSLA" and ch.action == "buy" for ch in changes)
    assert any(ch.ticker == "ROKU" and ch.action == "sell" for ch in changes)
    assert any(ch.ticker == "AIRO" and ch.action == "new" for ch in changes)
    assert any(ch.ticker == "SHOP" and ch.action == "exit" for ch in changes)


def test_diff_handles_spatial_etf_changes():
    old_snapshot = load_snapshot_csv(DATA_DIR / "ark_holdings_old" / "ARKX_2025-10-31.csv")
    new_snapshot = load_snapshot_csv(DATA_DIR / "ark_holdings_new" / "ARKX_2025-10-31.csv")

    changes = diff_snapshots(old_snapshot, new_snapshot, weight_threshold=0.0, share_threshold=0.0)

    assert any(ch.ticker == "RKLB UQ" and ch.action == "buy" for ch in changes)
    assert any(ch.ticker == "AVAV" and ch.action == "sell" for ch in changes)
    assert any(ch.ticker == "SKYW" and ch.action == "new" for ch in changes)
