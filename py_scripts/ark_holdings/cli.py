from __future__ import annotations

import argparse


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fetch, diff, and persist ARK ETF holdings snapshots.")
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
        "--summary-path", default="temp/ark_pipeline/diff_summary.md", help="Path to write Markdown summary of changes."
    )
    parser.add_argument(
        "--summary-json",
        default="temp/ark_pipeline/diff_summary.json",
        help="Path to write machine-readable JSON summary.",
    )
    parser.add_argument("--etfs", help="Comma separated ETF symbols to process (default: all).")
    parser.add_argument("--timeout", type=int, default=30, help="HTTP timeout seconds.")
    parser.add_argument("--top", type=int, default=10, help="Top N changes shown per ETF.")
    parser.add_argument(
        "--weight-threshold", type=float, default=1e-4, help="Minimum absolute weight change required to flag a diff."
    )
    parser.add_argument(
        "--share-threshold", type=float, default=1.0, help="Minimum absolute share change required to flag a diff."
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
        "--email-subject", default="ARK ETF Holdings Daily Update", help="Email subject when --send-email is enabled."
    )
    parser.add_argument(
        "--holdings-limit",
        type=int,
        default=20,
        help="Number of positions to show in holdings overview per ETF when emailing.",
    )
    return parser.parse_args()
