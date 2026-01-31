"""Logging configuration for Discord Assistant."""

import logging
import sys
from datetime import datetime
from pathlib import Path

from config import LOG_DIR


def setup_logging() -> logging.Logger:
    """Set up logging to both file and console."""
    logger = logging.getLogger("discord_assistant")
    logger.setLevel(logging.INFO)

    # Clear any existing handlers
    logger.handlers.clear()

    # File handler - dated log file
    log_file = LOG_DIR / f"{datetime.now().strftime('%Y-%m-%d')}.log"
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(logging.INFO)
    file_formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    file_handler.setFormatter(file_formatter)
    logger.addHandler(file_handler)

    # Console handler (only if not running as background)
    if sys.stdout is not None and sys.stdout.isatty():
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(logging.INFO)
        console_formatter = logging.Formatter(
            "%(asctime)s | %(levelname)-8s | %(message)s",
            datefmt="%H:%M:%S"
        )
        console_handler.setFormatter(console_formatter)
        logger.addHandler(console_handler)

    return logger


# Global logger instance
logger = setup_logging()
