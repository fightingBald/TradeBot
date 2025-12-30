from __future__ import annotations

import argparse
import json
import logging
import shutil
from dataclasses import dataclass
from pathlib import Path

from toolkits.ark.holdings import FUND_CSV, HoldingSnapshot, diff_snapshots, fetch_holdings_snapshot
from toolkits.ark.holdings.io import load_snapshot_folder, snapshot_collection_to_folder

from .email_report import EmailReportContext, _send_email_report
from .reporting import _build_etf_report, _build_global_summary, _json_default, _render_markdown

logger = logging.getLogger("ark_pipeline")


@dataclass(frozen=True)
class PipelineConfig:
    timeout: int
    weight_threshold: float
    share_threshold: float
    top_n: int


def _determine_symbols(symbols_arg: str | None) -> list[str]:
    if not symbols_arg:
        return list(FUND_CSV.keys())
    symbols = [token.strip().upper() for token in symbols_arg.split(",") if token.strip()]
    invalid = [symbol for symbol in symbols if symbol not in FUND_CSV]
    if invalid:
        raise ValueError(f"不支持的 ETF: {', '.join(invalid)}")
    return symbols


def _prepare_output_dir(output_dir: Path) -> None:
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)


def _collect_reports(
    symbols: list[str],
    baseline_snapshots: dict[str, HoldingSnapshot],
    *,
    config: PipelineConfig,
) -> tuple[dict[str, HoldingSnapshot], list[dict]]:
    new_snapshots: dict[str, HoldingSnapshot] = {}
    reports: list[dict] = []

    for symbol in symbols:
        logger.info("Fetching %s snapshot", symbol)
        snapshot = fetch_holdings_snapshot(symbol, timeout=config.timeout)
        new_snapshots[symbol] = snapshot

        baseline = baseline_snapshots.get(symbol)
        if baseline:
            changes = diff_snapshots(
                baseline, snapshot, weight_threshold=config.weight_threshold, share_threshold=config.share_threshold
            )
        else:
            changes = []

        report = _build_etf_report(symbol, baseline, snapshot, changes, config.top_n)
        reports.append(report)

    return new_snapshots, reports


def _write_summary_artifacts(
    *,
    reports: list[dict],
    global_summary: dict,
    summary_path: Path,
    summary_json_path: Path,
) -> None:
    markdown = _render_markdown(reports, global_summary)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(markdown, encoding="utf-8")
    logger.info("Wrote summary markdown: %s", summary_path)

    summary_json_path.parent.mkdir(parents=True, exist_ok=True)
    summary_json_path.write_text(
        json.dumps({"summary": global_summary, "etfs": reports}, ensure_ascii=False, indent=2, default=_json_default),
        encoding="utf-8",
    )
    logger.info("Wrote summary json: %s", summary_json_path)


def run_pipeline(args: argparse.Namespace) -> None:
    symbols = _determine_symbols(args.etfs)
    logger.info("Processing ETFs: %s", ", ".join(symbols))

    baseline_snapshots = load_snapshot_folder(args.baseline_dir)
    if baseline_snapshots:
        logger.info("Loaded baseline snapshots for: %s", ", ".join(sorted(baseline_snapshots)))
    else:
        logger.warning("No baseline snapshots found at %s (first run?)", args.baseline_dir)

    output_dir = Path(args.output_dir)
    _prepare_output_dir(output_dir)

    config = PipelineConfig(
        timeout=args.timeout,
        weight_threshold=args.weight_threshold,
        share_threshold=args.share_threshold,
        top_n=args.top,
    )
    new_snapshots, reports = _collect_reports(
        symbols,
        baseline_snapshots,
        config=config,
    )

    global_summary = _build_global_summary(reports)

    summary_path = Path(args.summary_path)
    summary_json_path = Path(args.summary_json)
    _write_summary_artifacts(
        reports=reports,
        global_summary=global_summary,
        summary_path=summary_path,
        summary_json_path=summary_json_path,
    )

    snapshot_collection_to_folder(new_snapshots, output_dir)
    logger.info("Prepared new baseline folder: %s", output_dir)

    if args.send_email:
        context = EmailReportContext(
            reports=reports,
            snapshots=new_snapshots,
            summary_markdown=summary_path,
            summary_json=summary_json_path,
            holdings_limit=args.holdings_limit,
            global_summary=global_summary,
        )
        _send_email_report(
            context=context,
            subject=args.email_subject,
            recipient_config_path=args.recipient_config,
        )
