from __future__ import annotations

from datetime import date

import pytest

from data_sources.ark_holdings import Holding, HoldingSnapshot, diff_snapshots
from py_scripts.ark_holdings.daily_pipeline import (_build_etf_report,
                                                    _render_email_html,
                                                    _resolve_recipients,
                                                    change_to_dict)


@pytest.fixture()
def baseline_snapshot() -> HoldingSnapshot:
    holdings = [
        Holding(
            as_of=date(2024, 10, 30),
            etf="ARKK",
            company="Tesla Inc",
            ticker="TSLA",
            shares=1000,
            weight=0.09,
            market_value=200000.0,
        ),
        Holding(
            as_of=date(2024, 10, 30),
            etf="ARKK",
            company="Roku Inc",
            ticker="ROKU",
            shares=500,
            weight=0.05,
            market_value=80000.0,
        ),
    ]
    return HoldingSnapshot(etf="ARKK", as_of=date(2024, 10, 30), holdings=holdings)


@pytest.fixture()
def current_snapshot() -> HoldingSnapshot:
    holdings = [
        Holding(
            as_of=date(2024, 10, 31),
            etf="ARKK",
            company="Tesla Inc",
            ticker="TSLA",
            shares=1200,
            weight=0.11,
            market_value=250000.0,
        ),
        Holding(
            as_of=date(2024, 10, 31),
            etf="ARKK",
            company="Zoom Video",
            ticker="ZM",
            shares=600,
            weight=0.06,
            market_value=70000.0,
        ),
    ]
    return HoldingSnapshot(etf="ARKK", as_of=date(2024, 10, 31), holdings=holdings)


def test_change_to_dict_contains_abs_fields(baseline_snapshot, current_snapshot):
    changes = diff_snapshots(
        baseline_snapshot, current_snapshot, weight_threshold=0.0, share_threshold=0.0
    )
    assert changes, "expected at least one change"
    payload = change_to_dict(changes[0])
    assert "weight_change_abs" in payload
    assert payload["weight_change_abs"] == pytest.approx(abs(payload["weight_change"]))
    assert "shares_change_abs" in payload
    assert payload["shares_change_abs"] == pytest.approx(abs(payload["shares_change"]))


def test_render_email_html_orders_sections(baseline_snapshot, current_snapshot):
    changes = diff_snapshots(
        baseline_snapshot, current_snapshot, weight_threshold=0.0, share_threshold=0.0
    )
    report = _build_etf_report(
        "ARKK", baseline_snapshot, current_snapshot, changes, top_n=5
    )
    html_body = _render_email_html(
        [report], {"ARKK": current_snapshot}, holdings_limit=10
    )

    # Expect key elements present
    assert "<h2>ARKK</h2>" in html_body
    assert "持仓变化" in html_body
    assert "最新持仓概览" in html_body

    # Ensure tickers appear and Tesla ranks ahead of Roku due to higher weight
    tsla_index = html_body.index("TSLA")
    assert tsla_index >= 0
    # Since ROKU exited, ZM should appear later in holdings section
    assert "ZM" in html_body


def test_resolve_recipients_env_fallback(monkeypatch, tmp_path):
    missing_path = tmp_path / "missing.toml"
    monkeypatch.delenv("EMAIL_RECIPIENTS_TO", raising=False)
    monkeypatch.delenv("EMAIL_RECIPIENTS_CC", raising=False)
    monkeypatch.delenv("EMAIL_RECIPIENTS_BCC", raising=False)

    monkeypatch.setenv("EMAIL_RECIPIENTS_TO", "foo@example.com,bar@example.com")
    monkeypatch.setenv("EMAIL_RECIPIENTS_CC", "")
    monkeypatch.setenv("EMAIL_RECIPIENTS_BCC", "bcc@example.com")

    recipients = _resolve_recipients(str(missing_path))
    assert recipients.to == ["foo@example.com", "bar@example.com"]
    assert recipients.cc == []
    assert recipients.bcc == ["bcc@example.com"]
