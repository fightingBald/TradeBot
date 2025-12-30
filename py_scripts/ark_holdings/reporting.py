from __future__ import annotations

import html
from collections.abc import Iterable, Sequence
from typing import Any

from toolkits.ark.holdings import HoldingSnapshot
from toolkits.ark.holdings.diff import HoldingChange

MIN_WEIGHT_EPSILON = 1e-9
MIN_SHARE_SIGNAL = 1.0


def change_to_dict(change: HoldingChange) -> dict[str, object]:
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


def _is_meaningful_change(change: HoldingChange | dict[str, Any]) -> bool:
    ticker = (getattr(change, "ticker", None) or change.get("ticker") if isinstance(change, dict) else "").strip()
    if not ticker or ticker.upper() == "NAN":
        return False
    weight_val = getattr(change, "weight_change", None) if not isinstance(change, dict) else change.get("weight_change")
    shares_val = getattr(change, "shares_change", None) if not isinstance(change, dict) else change.get("shares_change")
    weight = abs(weight_val or 0.0)
    shares = abs(shares_val or 0.0)
    return weight > MIN_WEIGHT_EPSILON or shares >= MIN_SHARE_SIGNAL


def _build_etf_report(
    symbol: str,
    baseline: HoldingSnapshot | None,
    current: HoldingSnapshot,
    changes: Sequence[HoldingChange],
    top_n: int,
) -> dict[str, object]:
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
        "new_positions": [change_to_dict(change) for change in filtered_changes if change.action == "new"],
        "exited_positions": [change_to_dict(change) for change in filtered_changes if change.action == "exit"],
    }
    return report


def _split_changes(changes: Sequence[HoldingChange]) -> tuple[list[HoldingChange], list[HoldingChange]]:
    buys: list[HoldingChange] = []
    sells: list[HoldingChange] = []
    for change in changes:
        if change.action in {"new", "buy"}:
            buys.append(change)
        elif change.action in {"exit", "sell"}:
            sells.append(change)
    buys.sort(key=lambda ch: abs(ch.weight_change), reverse=True)
    sells.sort(key=lambda ch: abs(ch.weight_change), reverse=True)
    return buys, sells


def _build_global_summary(reports: Sequence[dict]) -> dict[str, list[dict]]:
    buys = _aggregate_changes(reports, {"new", "buy"}, aggregate_action="buy")
    sells = _aggregate_changes(reports, {"sell", "exit"}, aggregate_action="sell")
    return {"buys": buys, "sells": sells}


def _aggregate_changes(reports: Sequence[dict], actions: set[str], *, aggregate_action: str) -> list[dict]:
    buckets: dict[tuple[str, str], dict] = {}
    for report in reports:
        for change in report["changes"]:
            if change.get("action") not in actions:
                continue
            if not _is_meaningful_change(change):
                continue
            shares_delta = abs(change.get("shares_change") or 0.0)
            if shares_delta < MIN_SHARE_SIGNAL:
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
    lines = ["# ARK Holdings Daily Diff", ""]
    lines.extend(_render_markdown_global(global_summary))
    lines.append("")
    for report in reports:
        lines.extend(_render_report_section(report))
    return "\n".join(lines).strip() + "\n"


def _render_report_section(report: dict) -> list[str]:
    lines = [f"## {report['etf']}", f"- 最新快照日期：{report['current_as_of']}"]
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
        table_entries = []
        for change in report["changes"]:
            copied = dict(change)
            copied.setdefault("etf", report["etf"])
            table_entries.append(copied)
        lines.append("")
        lines.append("### 持仓变化（按权重绝对值排序）")
        lines.extend(_render_markdown_table(_build_table_rows(table_entries, include_etf=True)))
    else:
        lines.append("")
        lines.append("> 无超过阈值的增减持。")

    lines.append("")
    return lines


def _build_table_rows(
    entries: Sequence[dict], *, include_etf: bool = False, include_flags: bool = False
) -> list[list[str]]:
    columns = ["Ticker", "Company", "Action", "Shares Δ", "Weight Δ (abs)", "MV Δ (abs)", "Net Weight Δ", "Net MV Δ"]
    if include_etf:
        columns.append("ETF")
    if include_flags:
        columns.extend(["新进?", "清仓?"])

    lines: list[str] = []
    lines.append("| " + " | ".join(columns) + " |")
    lines.append("| " + " | ".join(["---"] * len(columns)) + " |")

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
            etf_value = entry.get("etf")
            if etf_value:
                row.append(str(etf_value))
            else:
                row.append(_format_etf_contribs(entry))
        if include_flags:
            row.append("✅" if entry.get("is_new") else "")
            row.append("✅" if entry.get("is_exit") else "")
        lines.append("| " + " | ".join(row) + " |")
    return lines


def _render_markdown_table(lines: Sequence[str]) -> list[str]:
    return list(lines)


def _render_markdown_global(summary: dict) -> list[str]:
    lines: list[str] = ["## 全局持仓变化摘要", ""]
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


def _json_default(value: object) -> str:
    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()  # type: ignore[union-attr]
        except TypeError:
            pass
    return str(value)


def _display_delta(change: dict, key: str) -> float | None:
    value = change.get(key)
    if value is None:
        return None
    magnitude = abs(value)
    action = change.get("action")
    if action in {"new", "buy"}:
        return magnitude
    return -magnitude


def _format_etf_contribs(entry: dict, *, html_format: bool = False) -> str:
    contribs = entry.get("etf_contribs") or []
    parts = []
    for contrib in contribs:
        weight = _display_delta(contrib, "weight_change")
        if weight is None:
            continue
        label = f"{weight:+.4f}"
        etf_label = contrib.get("etf") or ""
        if html_format:
            etf_label = html_escape(etf_label)
        parts.append(f"{etf_label}({label})")
    if not parts:
        fallback = entry.get("etf") or ""
        return html_escape(fallback) if html_format else fallback
    return ", ".join(parts)


def html_escape(text: str) -> str:
    return html.escape(text or "")
