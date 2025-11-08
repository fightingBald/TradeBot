"""Daily pipeline: fetch ARK holdings, diff vs baseline, emit summaries."""

from __future__ import annotations

import argparse
import html
import json
import logging
import os
import shutil
from typing import Dict, Iterable, List, Sequence

from toolkits.ark.holdings import (FUND_CSV, HoldingSnapshot, diff_snapshots,
                                   fetch_holdings_snapshot)
from toolkits.ark.holdings.diff import HoldingChange
from toolkits.ark.holdings.io import (load_snapshot_folder,
                                      snapshot_collection_to_folder)
from toolkits.notifications import (EmailAttachment, EmailDeliveryError,
                                    EmailNotificationService, EmailSettings,
                                    RecipientConfig, load_recipient_config)

from toolkits.ark.holdings import (FUND_CSV, HoldingSnapshot, diff_snapshots,
                                   fetch_holdings_snapshot)
from toolkits.ark.holdings.diff import HoldingChange
from toolkits.ark.holdings.io import (load_snapshot_folder,
                                      snapshot_collection_to_folder)
from toolkits.notifications import (EmailAttachment, EmailDeliveryError,
                                    EmailNotificationService, EmailSettings,
                                    RecipientConfig, load_recipient_config)

logger = logging.getLogger("ark_pipeline")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fetch, diff, and persist ARK ETF holdings snapshots."
    )
    parser.add_argument(
        "--baseline-dir",
        default="baseline_snapshots",
        help="Existing baseline snapshot directory downloaded from artifact.",
    )
    parser.add_argument(
        "--output-dir",
        default="temp/ark_pipeline/latest_snapshots",
        help="Directory to store freshly fetched snapshots (also uploaded as new baseline).",
    )
    parser.add_argument(
        "--summary-path",
        default="temp/ark_pipeline/diff_summary.md",
        help="Path to write Markdown summary of changes.",
    )
    parser.add_argument(
        "--summary-json",
        default="temp/ark_pipeline/diff_summary.json",
        help="Path to write machine-readable JSON summary.",
    )
    parser.add_argument(
        "--etfs",
        help="Comma separated ETF symbols to process (default: all).",
    )
    parser.add_argument("--timeout", type=int, default=30, help="HTTP timeout seconds.")
    parser.add_argument(
        "--top", type=int, default=10, help="Top N changes shown per ETF."
    )
    parser.add_argument(
        "--weight-threshold",
        type=float,
        default=1e-4,
        help="Minimum absolute weight change required to flag a diff.",
    )
    parser.add_argument(
        "--share-threshold",
        type=float,
        default=1.0,
        help="Minimum absolute share change required to flag a diff.",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Logging verbosity.",
    )
    parser.add_argument(
        "--send-email",
        action="store_true",
        help="Send summary email using notification module (requires EMAIL_* env vars).",
    )
    parser.add_argument(
        "--recipient-config",
        default="config/notification_recipients.toml",
        help="Path to recipient TOML (used when --send-email).",
    )
    parser.add_argument(
        "--email-subject",
        default="ARK ETF Holdings Daily Update",
        help="Email subject when --send-email is enabled.",
    )
    parser.add_argument(
        "--holdings-limit",
        type=int,
        default=20,
        help="Number of positions to show in holdings overview per ETF when emailing.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    logging.basicConfig(level=getattr(logging, args.log_level))

    symbols = _determine_symbols(args.etfs)
    logger.info("Processing ETFs: %s", ", ".join(symbols))

    baseline_snapshots = load_snapshot_folder(args.baseline_dir)
    if baseline_snapshots:
        logger.info(
            "Loaded baseline snapshots for: %s", ", ".join(sorted(baseline_snapshots))
        )
    else:
        logger.warning(
            "No baseline snapshots found at %s (first run?)", args.baseline_dir
        )

    output_dir = Path(args.output_dir)
    if output_dir.exists():
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    new_snapshots = {}
    reports = []

    for symbol in symbols:
        logger.info("Fetching %s snapshot", symbol)
        snapshot = fetch_holdings_snapshot(symbol, timeout=args.timeout)
        new_snapshots[symbol] = snapshot

        baseline = baseline_snapshots.get(symbol)
        if baseline:
            changes = diff_snapshots(
                baseline,
                snapshot,
                weight_threshold=args.weight_threshold,
                share_threshold=args.share_threshold,
            )
        else:
            changes = []

        report = _build_etf_report(symbol, baseline, snapshot, changes, args.top)
        reports.append(report)

    global_summary = _build_global_summary(reports)

    markdown = _render_markdown(reports, global_summary)
    summary_path = Path(args.summary_path)
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(markdown, encoding="utf-8")
    logger.info("Wrote summary markdown: %s", summary_path)

    summary_json_path = Path(args.summary_json)
    summary_json_path.parent.mkdir(parents=True, exist_ok=True)
    summary_json_path.write_text(
        json.dumps(
            {"summary": global_summary, "etfs": reports},
            ensure_ascii=False,
            indent=2,
            default=_json_default,
        ),
        encoding="utf-8",
    )
    logger.info("Wrote summary json: %s", summary_json_path)

    snapshot_collection_to_folder(new_snapshots, output_dir)
    logger.info("Prepared new baseline folder: %s", output_dir)

    if args.send_email:
        _send_email_report(
            reports=reports,
            snapshots=new_snapshots,
            subject=args.email_subject,
            recipient_config_path=args.recipient_config,
            summary_markdown=summary_path,
            summary_json=summary_json_path,
            holdings_limit=args.holdings_limit,
            global_summary=global_summary,
        )


def _determine_symbols(symbols_arg: str | None) -> List[str]:
    if not symbols_arg:
        return list(FUND_CSV.keys())
    symbols = [
        token.strip().upper() for token in symbols_arg.split(",") if token.strip()
    ]
    invalid = [symbol for symbol in symbols if symbol not in FUND_CSV]
    if invalid:
        raise ValueError(f"不支持的 ETF: {', '.join(invalid)}")
    return symbols


def _build_etf_report(
    symbol: str,
    baseline: HoldingSnapshot | None,
    current: HoldingSnapshot,
    changes: Sequence[HoldingChange],
    top_n: int,
) -> dict:
    filtered_changes = [change for change in changes if _is_meaningful_change(change)]
    buys, sells = _split_changes(filtered_changes)
    report = {
        "etf": symbol,
        "current_as_of": current.as_of.isoformat(),
        "baseline_as_of": baseline.as_of.isoformat() if baseline else None,
        "total_holdings": len(current.holdings),
        "changes": [change_to_dict(change) for change in filtered_changes],
        "top_buys": [change_to_dict(change) for change in buys[:top_n]],
        "top_sells": [change_to_dict(change) for change in sells[:top_n]],
        "new_positions": [
            change_to_dict(change)
            for change in filtered_changes
            if change.action == "new"
        ],
        "exited_positions": [
            change_to_dict(change)
            for change in filtered_changes
            if change.action == "exit"
        ],
    }
    return report


def _split_changes(
    changes: Sequence[HoldingChange],
) -> tuple[List[HoldingChange], List[HoldingChange]]:
    buys: List[HoldingChange] = []
    sells: List[HoldingChange] = []
    for change in changes:
        if change.action in {"new", "buy"}:
            buys.append(change)
        elif change.action in {"exit", "sell"}:
            sells.append(change)
    buys.sort(key=lambda ch: abs(ch.weight_change), reverse=True)
    sells.sort(key=lambda ch: abs(ch.weight_change), reverse=True)
    return buys, sells


def change_to_dict(change: HoldingChange) -> Dict[str, object]:
    weight_change = change.weight_change or 0.0
    shares_change = change.shares_change or 0.0
    return {
        "etf": change.etf,
        "action": change.action,
        "ticker": change.ticker,
        "company": change.company,
        "shares_change": shares_change,
        "weight_change": weight_change,
        "weight_change_abs": abs(weight_change),
        "shares_change_abs": abs(shares_change),
        "market_value_change": change.market_value_change,
        "is_new": change.action == "new",
        "is_exit": change.action == "exit",
        "previous": change.previous.model_dump() if change.previous else None,
        "current": change.current.model_dump() if change.current else None,
    }


def _is_meaningful_change(change) -> bool:
    ticker = (getattr(change, "ticker", None) or change.get("ticker") if isinstance(change, dict) else ""
    ).strip()
    if not ticker or ticker.upper() == "NAN":
        return False
    weight_val = getattr(change, "weight_change", None) if not isinstance(change, dict) else change.get("weight_change")
    shares_val = getattr(change, "shares_change", None) if not isinstance(change, dict) else change.get("shares_change")
    weight = abs(weight_val or 0.0)
    shares = abs(shares_val or 0.0)
    return weight > 1e-9 or shares >= 1.0


def _build_global_summary(reports: Sequence[dict]) -> dict:
    buys = _aggregate_changes(reports, {"new", "buy"}, aggregate_action="buy")
    sells = _aggregate_changes(reports, {"sell", "exit"}, aggregate_action="sell")
    return {"buys": buys, "sells": sells}


def _aggregate_changes(
    reports: Sequence[dict],
    actions: set[str],
    *,
    aggregate_action: str,
) -> List[dict]:
    buckets: Dict[tuple[str, str], dict] = {}
    for report in reports:
        for change in report["changes"]:
            if change.get("action") not in actions:
                continue
            if not _is_meaningful_change(change):
                continue
            shares_delta = abs(change.get("shares_change") or 0.0)
            if shares_delta < 1.0:
                continue
            ticker = change.get("ticker") or ""
            company = change.get("company") or ""
            key = (ticker, company)
            bucket = buckets.setdefault(
                key,
                {
                    "ticker": ticker,
                    "company": company,
                    "action": aggregate_action,
                    "shares_change": 0.0,
                    "weight_change_abs": 0.0,
                    "weight_change_net": 0.0,
                    "market_value_change_abs": 0.0,
                    "market_value_change_net": 0.0,
                    "is_new": False,
                    "is_exit": False,
                    "etf_contribs": [],
                },
            )
            bucket["shares_change"] += shares_delta
            weight_delta = change.get("weight_change") or 0.0
            mv_delta = change.get("market_value_change") or 0.0
            bucket["weight_change_abs"] += abs(weight_delta)
            bucket["weight_change_net"] += weight_delta
            bucket["market_value_change_abs"] += abs(mv_delta)
            bucket["market_value_change_net"] += mv_delta
            bucket["is_new"] = bucket["is_new"] or change.get("is_new")
            bucket["is_exit"] = bucket["is_exit"] or change.get("is_exit")
            bucket["etf_contribs"].append(
                {
                    "etf": change.get("etf") or report["etf"],
                    "action": change.get("action"),
                    "weight_change": change.get("weight_change"),
                    "shares_change": change.get("shares_change"),
                    "market_value_change": change.get("market_value_change"),
                }
            )
    aggregated = list(buckets.values())
    aggregated.sort(key=lambda entry: abs(entry.get("weight_change_net") or 0.0), reverse=True)
    return aggregated


def _render_markdown(reports: Iterable[dict], global_summary: dict) -> str:
    lines = [
        "# ARK Holdings Daily Diff",
        "",
    ]
    lines.extend(_render_markdown_global(global_summary))
    lines.append("")
    for report in reports:
        lines.extend(_render_report_section(report))
    return "\n".join(lines).strip() + "\n"


def _render_report_section(report: dict) -> List[str]:
    lines = [
        f"## {report['etf']}",
        f"- 最新快照日期：{report['current_as_of']}",
    ]
    baseline_as_of = report.get("baseline_as_of")
    if baseline_as_of:
        lines.append(f"- 基线快照日期：{baseline_as_of}")
    else:
        lines.append("- 基线快照缺失（首次运行？）")

    total_changes = len(report["changes"])
    lines.append(f"- 检测到的变更总数：{total_changes}")
    lines.append(f"- 持仓总数：{report['total_holdings']}")

    new_positions = report["new_positions"]
    exited_positions = report["exited_positions"]
    lines.append(f"- 新进标的：{len(new_positions)} 个")
    lines.append(f"- 清仓标的：{len(exited_positions)} 个")

    if report["changes"]:
        lines.append("")
        lines.append("### 持仓变化（按权重绝对值排序）")
        lines.extend(_render_markdown_table(_build_table_rows(report["changes"], include_etf=True)))
    else:
        lines.append("")
        lines.append("> 无超过阈值的增减持。")

    lines.append("")
    return lines


def _build_table_rows(entries: Sequence[dict], *, include_etf: bool = False, include_flags: bool = False) -> List[List[str]]:
    header = ["Ticker", "Company", "Action", "Shares Δ", "Weight Δ (abs)", "MV Δ (abs)", "Net Weight Δ", "Net MV Δ"]
    if include_etf:
        header.append("ETF")
    if include_flags:
        header.extend(["新进?", "清仓?"])

    rows: List[List[str]] = [
        [f"| {' | '.join(header)} |"]
    ]
    separator = "| " + " | ".join(["---"] * len(header)) + " |"
    rows.append([separator])

    for entry in entries:
        shares_abs = _display_delta(entry, "shares_change")
        weight_abs = _display_delta(entry, "weight_change")
        mv_abs = _display_delta(entry, "market_value_change")
        mv_abs_display = f"${mv_abs:,.0f}" if mv_abs is not None else "N/A"
        weight_net = entry.get("weight_change") or 0.0
        mv_net = entry.get("market_value_change")
        mv_net_display = f"${mv_net:,.0f}" if mv_net is not None else "N/A"
        row = [
            entry.get("ticker", "-"),
            entry.get("company", "-"),
            entry.get("action", "-"),
            f"{shares_abs:,.0f}",
            f"{weight_abs:.4f}",
            mv_abs_display,
            f"{float(weight_net):+.4f}",
            mv_net_display,
        ]
        if include_etf:
            row.append(entry.get("etf", "-"))
        if include_flags:
            row.append("✅" if entry.get("is_new") else "")
            row.append("✅" if entry.get("is_exit") else "")
        rows.append(["| " + " | ".join(row) + " |"])
    return rows


def _render_markdown_global(summary: dict) -> List[str]:
    lines: List[str] = ["## 全局持仓变化摘要", ""]
    buys = summary.get("buys", [])
    sells = summary.get("sells", [])

    if buys:
        lines.append("### 增持明细")
        lines.extend(_render_markdown_table(_build_table_rows(buys, include_etf=True, include_flags=True)))
        lines.append("")
    else:
        lines.append("- 增持：无显著变动")

    if sells:
        lines.append("### 减持明细")
        lines.extend(_render_markdown_table(_build_table_rows(sells, include_etf=True, include_flags=True)))
        lines.append("")
    else:
        lines.append("- 减持：无显著变动")

    return lines


def _json_default(value):
    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()
        except TypeError:
            pass
    return str(value)


def _send_email_report(
    *,
    reports: Sequence[dict],
    snapshots: Dict[str, HoldingSnapshot],
    subject: str,
    recipient_config_path: str,
    summary_markdown: Path,
    summary_json: Path,
    holdings_limit: int,
    global_summary: dict,
) -> None:
    recipients = _resolve_recipients(recipient_config_path)
    if not recipients.to and not recipients.cc and not recipients.bcc:
        logger.warning("收件人列表为空，跳过发送邮件。")
        return

    _sanitize_email_environment()
    try:
        settings = EmailSettings()
    except Exception as exc:  # pragma: no cover - settings validation
        logger.error("邮件配置加载失败：%s", exc)
        raise

    service = EmailNotificationService(settings)
    body_html = _render_email_html(
        reports,
        snapshots,
        holdings_limit=holdings_limit,
        global_summary=global_summary,
    )

    attachments: List[EmailAttachment] = []
    if summary_markdown.exists():
        attachments.append(
            EmailAttachment(
                filename=summary_markdown.name,
                content=summary_markdown.read_bytes(),
                mimetype="text/markdown",
            )
        )
    if summary_json.exists():
        attachments.append(
            EmailAttachment(
                filename=summary_json.name,
                content=summary_json.read_bytes(),
                mimetype="application/json",
            )
        )

    logger.info("Sending email to %d recipients", len(recipients.to))
    try:
        service.send_email(
            subject=subject,
            body=body_html,
            subtype="html",
            recipients=recipients.to,
            cc=recipients.cc,
            bcc=recipients.bcc,
            attachments=attachments,
        )
    except EmailDeliveryError as exc:
        logger.error("邮件发送失败：%s", exc)
        raise


def _render_email_html(
    reports: Sequence[dict],
    snapshots: Dict[str, HoldingSnapshot],
    *,
    holdings_limit: int,
    global_summary: dict,
) -> str:
    lines: List[str] = [
        "<html><body>",
        "<h1>ARK Holdings Daily Diff</h1>",
    ]
    lines.extend(_render_email_global(global_summary))
    for report in reports:
        etf = html.escape(report["etf"])
        lines.append(f"<h2>{etf}</h2>")
        lines.append("<ul>")
        lines.append(f"<li>最新快照日期：{html.escape(report['current_as_of'])}</li>")
        baseline_as_of = report.get("baseline_as_of")
        if baseline_as_of:
            lines.append(f"<li>基线快照日期：{html.escape(baseline_as_of)}</li>")
        else:
            lines.append("<li>基线快照缺失（首次运行？）</li>")
        lines.append(f"<li>检测到的变更总数：{len(report['changes'])}</li>")
        lines.append(f"<li>持仓总数：{report['total_holdings']}</li>")
        lines.append(f"<li>新进标的：{len(report['new_positions'])} 个</li>")
        lines.append(f"<li>清仓标的：{len(report['exited_positions'])} 个</li>")
        lines.append("</ul>")

        sorted_changes = sorted(
            report["changes"],
            key=lambda entry: entry.get("weight_change_abs", 0.0),
            reverse=True,
        )
        if sorted_changes:
            lines.append("<h3>持仓变化（按权重绝对值排序）</h3>")
            lines.append(
                "<table border='1' cellpadding='4' cellspacing='0'>"
                "<thead><tr>"
                "<th>Ticker</th><th>Company</th><th>Action</th>"
                "<th>Shares Δ</th><th>Weight Δ</th><th>MV Δ</th>"
                "</tr></thead><tbody>"
            )
            for change in sorted_changes:
                weight = change.get("weight_change", 0.0) or 0.0
                shares = change.get("shares_change", 0.0) or 0.0
                mv = change.get("market_value_change")
                mv_display = f"${mv:,.0f}" if mv is not None else "N/A"
                lines.append(
                    "<tr>"
                    f"<td>{html.escape(change['ticker'])}</td>"
                    f"<td>{html.escape(change['company'])}</td>"
                    f"<td>{html.escape(change['action'])}</td>"
                    f"<td>{shares:,.0f}</td>"
                    f"<td>{weight:.4f}</td>"
                    f"<td>{mv_display}</td>"
                    "</tr>"
                )
            lines.append("</tbody></table>")
        else:
            lines.append("<p>无超过阈值的持仓变化。</p>")

        snapshot = snapshots.get(report["etf"])
        if snapshot:
            lines.append(f"<h3>最新持仓概览（权重 Top {holdings_limit}）</h3>")
            holdings_sorted = sorted(
                snapshot.holdings, key=lambda h: h.weight or 0.0, reverse=True
            )
            lines.append(
                "<table border='1' cellpadding='4' cellspacing='0'>"
                "<thead><tr>"
                "<th>#</th><th>Ticker</th><th>Company</th><th>Weight</th><th>Shares</th><th>Market Value</th>"
                "</tr></thead><tbody>"
            )
            for idx, holding in enumerate(holdings_sorted[:holdings_limit], start=1):
                weight = (holding.weight or 0.0) * 100
                shares = holding.shares or 0.0
                mv = holding.market_value
                mv_display = f"${mv:,.0f}" if mv is not None else "N/A"
                lines.append(
                    "<tr>"
                    f"<td>{idx}</td>"
                    f"<td>{html.escape(holding.ticker)}</td>"
                    f"<td>{html.escape(holding.company)}</td>"
                    f"<td>{weight:.2f}%</td>"
                    f"<td>{shares:,.0f}</td>"
                    f"<td>{mv_display}</td>"
                    "</tr>"
                )
            lines.append("</tbody></table>")
        lines.append("<hr/>")
    lines.append("</body></html>")
    return "\n".join(lines)


def _render_email_global(summary: dict) -> List[str]:
    lines: List[str] = ["<h2>全局持仓变化摘要</h2>"]
    buys = summary.get("buys", [])
    sells = summary.get("sells", [])

    if buys:
        lines.append("<h3>增持明细</h3>")
        lines.append(_format_global_html_table(buys, include_new=True))
    else:
        lines.append("<p>增持：无显著变动。</p>")

    if sells:
        lines.append("<h3>减持明细</h3>")
        lines.append(_format_global_html_table(sells, include_exit=True))
    else:
        lines.append("<p>减持：无显著变动。</p>")

    lines.append("<hr/>")
    return lines


def _format_global_html_table(
    entries: Sequence[dict],
    *,
    include_new: bool = False,
    include_exit: bool = False,
) -> str:
    header_extra = "新进?" if include_new else "清仓?" if include_exit else ""
    rows = [
        "<table border='1' cellpadding='4' cellspacing='0'>",
        "<thead><tr>"
        "<th>Ticker</th><th>Company</th><th>Action</th>"
        "<th>Shares Δ</th><th>Weight Δ (abs)</th><th>MV Δ (abs)</th>"
        "<th>Net Weight Δ</th><th>Net MV Δ</th><th>ETF</th>"
        f"<th>{header_extra}</th>"
        "</tr></thead><tbody>",
    ]
    for entry in entries:
        shares = entry.get("shares_change") or 0.0
        weight_abs = entry.get("weight_change_abs") or 0.0
        mv_abs = entry.get("market_value_change_abs") or 0.0
        weight_net = entry.get("weight_change_net") or 0.0
        mv_net = entry.get("market_value_change_net")
        mv_abs_display = f"${mv_abs:,.0f}"
        mv_net_display = f"${mv_net:,.0f}" if mv_net is not None else "N/A"
        indicator = ""
        if include_new:
            indicator = "✅" if entry.get("is_new") else ""
        elif include_exit:
            indicator = "✅" if entry.get("is_exit") else ""
        rows.append(
            "<tr>"
            f"<td>{html_escape(entry['ticker'])}</td>"
            f"<td>{html_escape(entry['company'])}</td>"
            f"<td>{html_escape(entry['action'])}</td>"
            f"<td>{shares:,.0f}</td>"
            f"<td>{weight_abs:.4f}</td>"
            f"<td>{mv_abs_display}</td>"
            f"<td>{weight_net:+.4f}</td>"
            f"<td>{mv_net_display}</td>"
            f"<td>{html_escape(_format_etf_contribs(entry, html=True))}</td>"
            f"<td>{indicator}</td>"
            "</tr>"
        )
    rows.append("</tbody></table>")
    return "\n".join(rows)


def _display_delta(change: dict, key: str) -> float | None:
    value = change.get(key)
    if value is None:
        return None
    magnitude = abs(value)
    action = change.get("action")
    if action in {"new", "buy"}:
        return magnitude
    return -magnitude


def _format_etf_contribs(entry: dict, *, html: bool = False) -> str:
    contribs = entry.get("etf_contribs") or []
    parts = []
    for contrib in contribs:
        weight = _display_delta(contrib, "weight_change")
        if weight is None:
            continue
        label = f"{weight:+.4f}"
        etf_label = contrib.get("etf") or ""
        if html:
            etf_label = html_escape(etf_label)
        parts.append(f"{etf_label}({label})")
    if not parts:
        fallback = entry.get("etf") or ""
        return html_escape(fallback) if html else fallback
    return ", ".join(parts)


def html_escape(text: str) -> str:
    return html.escape(text or "")


def _resolve_recipients(recipient_config_path: str) -> RecipientConfig:
    """Load recipient configuration from file or EMAIL_RECIPIENTS_* environment variables."""
    env_to = os.environ.get("EMAIL_RECIPIENTS_TO", "")
    env_cc = os.environ.get("EMAIL_RECIPIENTS_CC", "")
    env_bcc = os.environ.get("EMAIL_RECIPIENTS_BCC", "")

    try:
        return load_recipient_config(recipient_config_path)
    except FileNotFoundError:
        logger.info(
            "Recipient config file missing at %s, fallback to EMAIL_RECIPIENTS_* env variables.",
            recipient_config_path,
        )
    except ValueError:
        raise

    if not any([env_to.strip(), env_cc.strip(), env_bcc.strip()]):
        raise FileNotFoundError(
            f"找不到收件人配置文件：{recipient_config_path}，且未设置 EMAIL_RECIPIENTS_* 环境变量"
        )

    return RecipientConfig.model_validate(
        {
            "to": _split_addresses(env_to),
            "cc": _split_addresses(env_cc),
            "bcc": _split_addresses(env_bcc),
        }
    )


def _split_addresses(raw: str) -> List[str]:
    if not raw:
        return []
    return [addr.strip() for addr in raw.split(",") if addr.strip()]


def _sanitize_email_environment() -> None:
    """Remove empty EMAIL_* values to avoid pydantic parsing errors."""
    for key in (
        "EMAIL_HOST",
        "EMAIL_PORT",
        "EMAIL_SENDER",
        "EMAIL_USE_TLS",
        "EMAIL_USE_SSL",
        "EMAIL_MAX_RETRIES",
        "EMAIL_USERNAME",
        "EMAIL_PASSWORD",
    ):
        value = os.environ.get(key)
        if value is not None and value.strip() == "":
            del os.environ[key]


if __name__ == "__main__":
    main()
