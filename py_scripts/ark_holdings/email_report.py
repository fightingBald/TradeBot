from __future__ import annotations

import logging
import os
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from toolkits.ark.holdings import HoldingSnapshot
from toolkits.notifications import (
    EmailAttachment,
    EmailDeliveryError,
    EmailMessageOptions,
    EmailNotificationService,
    EmailRecipients,
    EmailSettings,
    RecipientConfig,
    load_recipient_config,
)

from .reporting import _format_etf_contribs, html_escape

logger = logging.getLogger("ark_pipeline")


@dataclass(slots=True)
class EmailReportContext:
    """Aggregates artifacts needed for the notification email."""

    reports: Sequence[dict]
    snapshots: dict[str, HoldingSnapshot]
    summary_markdown: Path
    summary_json: Path
    holdings_limit: int
    global_summary: dict


def _send_email_report(*, context: EmailReportContext, subject: str, recipient_config_path: str) -> None:
    recipients_cfg = _resolve_recipients(recipient_config_path)
    if not recipients_cfg.to:
        logger.warning("主送收件人为空，跳过发送邮件。")
        return

    _sanitize_email_environment()
    try:
        settings = EmailSettings()
    except Exception as exc:  # pragma: no cover - settings validation
        logger.error("邮件配置加载失败：%s", exc)
        raise

    service = EmailNotificationService(settings)
    body_html = _render_email_html(
        context.reports, context.snapshots, holdings_limit=context.holdings_limit, global_summary=context.global_summary
    )

    attachments: list[EmailAttachment] = []
    if context.summary_markdown.exists():
        attachments.append(
            EmailAttachment(
                filename=context.summary_markdown.name,
                content=context.summary_markdown.read_bytes(),
                mimetype="text/markdown",
            )
        )
    if context.summary_json.exists():
        attachments.append(
            EmailAttachment(
                filename=context.summary_json.name,
                content=context.summary_json.read_bytes(),
                mimetype="application/json",
            )
        )

    email_recipients = EmailRecipients(
        to=recipients_cfg.to, cc=recipients_cfg.cc or None, bcc=recipients_cfg.bcc or None
    )

    logger.info("Sending email to %d recipients", len(email_recipients.to))
    try:
        service.send_email(
            subject=subject,
            body=body_html,
            recipients=email_recipients,
            options=EmailMessageOptions(subtype="html", attachments=attachments),
        )
    except EmailDeliveryError as exc:
        logger.error("邮件发送失败：%s", exc)
        raise


def _render_email_html(
    reports: Sequence[dict], snapshots: dict[str, HoldingSnapshot], *, holdings_limit: int, global_summary: dict
) -> str:
    lines: list[str] = ["<html><body>", "<h1>ARK Holdings Daily Diff</h1>"]
    lines.extend(_render_email_global(global_summary))
    for report in reports:
        etf = html_escape(report["etf"])
        lines.append(f"<h2>{etf}</h2>")
        lines.append("<ul>")
        lines.append(f"<li>最新快照日期：{html_escape(report['current_as_of'])}</li>")
        baseline_as_of = report.get("baseline_as_of")
        if baseline_as_of:
            lines.append(f"<li>基线快照日期：{html_escape(baseline_as_of)}</li>")
        else:
            lines.append("<li>基线快照缺失（首次运行？）</li>")
        lines.append(f"<li>检测到的变更总数：{len(report['changes'])}</li>")
        lines.append(f"<li>持仓总数：{report['total_holdings']}</li>")
        lines.append(f"<li>新进标的：{len(report['new_positions'])} 个</li>")
        lines.append(f"<li>清仓标的：{len(report['exited_positions'])} 个</li>")
        lines.append("</ul>")

        sorted_changes = sorted(report["changes"], key=lambda entry: entry.get("weight_change_abs", 0.0), reverse=True)
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
                    f"<td>{html_escape(change['ticker'])}</td>"
                    f"<td>{html_escape(change['company'])}</td>"
                    f"<td>{html_escape(change['action'])}</td>"
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
            holdings_sorted = sorted(snapshot.holdings, key=lambda h: h.weight or 0.0, reverse=True)
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
                    f"<td>{html_escape(holding.ticker)}</td>"
                    f"<td>{html_escape(holding.company)}</td>"
                    f"<td>{weight:.2f}%</td>"
                    f"<td>{shares:,.0f}</td>"
                    f"<td>{mv_display}</td>"
                    "</tr>"
                )
            lines.append("</tbody></table>")
        lines.append("<hr/>")
    lines.append("</body></html>")
    return "\n".join(lines)


def _render_email_global(summary: dict) -> list[str]:
    lines: list[str] = ["<h2>全局持仓变化摘要</h2>"]
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


def _format_global_html_table(entries: Sequence[dict], *, include_new: bool = False, include_exit: bool = False) -> str:
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
            f"<td>{html_escape(_format_etf_contribs(entry, html_format=True))}</td>"
            f"<td>{indicator}</td>"
            "</tr>"
        )
    rows.append("</tbody></table>")
    return "\n".join(rows)


def _resolve_recipients(recipient_config_path: str) -> RecipientConfig:
    """Load recipient configuration from file or EMAIL_RECIPIENTS_* environment variables."""
    env_to = os.environ.get("EMAIL_RECIPIENTS_TO", "")
    env_cc = os.environ.get("EMAIL_RECIPIENTS_CC", "")
    env_bcc = os.environ.get("EMAIL_RECIPIENTS_BCC", "")

    try:
        return load_recipient_config(recipient_config_path)
    except FileNotFoundError:
        logger.info(
            "Recipient config file missing at %s, fallback to EMAIL_RECIPIENTS_* env variables.", recipient_config_path
        )
    except ValueError:
        raise

    if not any([env_to.strip(), env_cc.strip(), env_bcc.strip()]):
        raise FileNotFoundError(f"找不到收件人配置文件：{recipient_config_path}，且未设置 EMAIL_RECIPIENTS_* 环境变量")

    return RecipientConfig.model_validate(
        {"to": _split_addresses(env_to), "cc": _split_addresses(env_cc), "bcc": _split_addresses(env_bcc)}
    )


def _split_addresses(raw: str) -> list[str]:
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
