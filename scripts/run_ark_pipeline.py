"""Helper executed by GitHub Actions to run the ARK holdings daily pipeline.

It reads configuration from environment variables, derives sensible defaults,
and then delegates to ``py_scripts.ark_holdings.daily_pipeline`` with the right
command-line arguments.  This keeps the workflow YAML lean and centralises the
environment handling logic.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
import shutil


def _get_env(name: str, default: str | None = None) -> str:
    value = os.environ.get(name)
    if value is None:
        return default or ""
    return value


def _parse_bool(value: str, *, default: bool = False) -> bool:
    if not value:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def _parse_int(value: str, *, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _determine_weight_threshold(min_weight_bp: str) -> float:
    bp = _parse_int(min_weight_bp, default=1)
    return bp / 10_000.0


def _normalise_fund_list(raw: str) -> str:
    if not raw:
        return ""
    parts = [token.strip().upper() for token in raw.split(",") if token.strip()]
    return ",".join(parts)


def run() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo_root))
    src_dir = repo_root / "src"
    if src_dir.exists():
        sys.path.insert(0, str(src_dir))

    from py_scripts.ark_holdings.daily_pipeline import main as pipeline_main  # noqa: WPS433

    baseline_artifact = _get_env("BASELINE_ARTIFACT_NAME", "ark-holdings-baseline")
    baseline_dir_name = _get_env("BASELINE_DIR", "baseline")
    output_dir = _get_env("OUTPUT_DIR", "temp/ark_pipeline/latest_snapshots")
    fund_list = _normalise_fund_list(_get_env("FUND_LIST", ""))
    min_weight_bp = _get_env("MIN_WEIGHT_BP", "1")
    min_share_delta = _get_env("MIN_SHARE_DELTA", "1")
    holdings_limit = _parse_int(_get_env("HOLDINGS_LIMIT", "25"), default=25)
    send_email = _parse_bool(_get_env("EMAIL_ENABLED", "true"), default=True)

    baseline_path = _resolve_baseline_path(baseline_dir_name, baseline_artifact)
    summary_path = Path("temp/ark_pipeline/diff_summary.md")
    summary_json_path = Path("temp/ark_pipeline/diff_summary.json")

    args = [
        "daily_pipeline",
        "--baseline-dir",
        str(baseline_path),
        "--output-dir",
        output_dir,
        "--summary-path",
        str(summary_path),
        "--summary-json",
        str(summary_json_path),
        "--share-threshold",
        min_share_delta,
        "--weight-threshold",
        f"{_determine_weight_threshold(min_weight_bp):.6f}",
        "--holdings-limit",
        str(holdings_limit),
        "--recipient-config",
        "config/notification_recipients.toml",
    ]

    if fund_list:
        args.extend(["--etfs", fund_list])

    if send_email:
        args.append("--send-email")

    sys.argv = args
    pipeline_main()

    # 清理旧的基线目录，避免在下一次运行时混淆
    baseline_root = Path("baseline")
    if baseline_root.exists():
        shutil.rmtree(baseline_root, ignore_errors=True)


def _resolve_baseline_path(baseline_dir_name: str, baseline_artifact: str) -> Path:
    baseline_root = Path("baseline")
    primary = baseline_root / baseline_dir_name
    fallback = baseline_root / baseline_artifact / baseline_dir_name
    if primary.exists():
        return primary
    if fallback.exists():
        return fallback
    # 如果都不存在，返回 primary 路径（管道内部会处理“首次运行”场景）
    return primary


if __name__ == "__main__":  # pragma: no cover - invoked by workflow
    run()
