"""Daily pipeline: fetch ARK holdings, diff vs baseline, emit summaries."""

from __future__ import annotations

import logging

from .cli import parse_args
from .email_report import _render_email_html, _resolve_recipients, _sanitize_email_environment
from .pipeline import run_pipeline
from .reporting import _build_etf_report, _build_global_summary, change_to_dict


def main() -> None:
    args = parse_args()
    logging.basicConfig(level=getattr(logging, args.log_level))
    run_pipeline(args)


__all__ = [
    "_build_etf_report",
    "_build_global_summary",
    "_render_email_html",
    "_resolve_recipients",
    "_sanitize_email_environment",
    "change_to_dict",
    "main",
]


if __name__ == "__main__":
    main()
