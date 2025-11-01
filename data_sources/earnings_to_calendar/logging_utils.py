"""Centralized logging helpers."""

import logging

LOGGER_NAME = "earnings_to_calendar"


def get_logger() -> logging.Logger:
    return logging.getLogger(LOGGER_NAME)
