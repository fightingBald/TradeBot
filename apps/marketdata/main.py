from __future__ import annotations

import logging

from apps.marketdata.streams import run_marketdata_stream
from core.settings import Settings

logger = logging.getLogger(__name__)


def _configure_logging() -> None:
    root_logger = logging.getLogger()
    if root_logger.handlers:
        return
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )


def run_marketdata() -> None:
    settings = Settings()
    logger.info(
        "Market data daemon starting profile=%s feed=%s symbols=%s",
        settings.engine_profile_id,
        settings.data_feed,
        ",".join(settings.marketdata_symbols),
    )
    run_marketdata_stream(settings)


def main() -> None:
    _configure_logging()
    run_marketdata()


if __name__ == "__main__":
    main()


__all__ = ["main", "run_marketdata"]
