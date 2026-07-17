"""
Reusable logging utility for the Student Support Services AI Chatbot.

Provides a configured logger with both console and file handlers.
Log files are written under the project's logs/ directory.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

from config.settings import get_settings

_LOGGERS: dict[str, logging.Logger] = {}


def get_logger(name: str = "student_support_chatbot") -> logging.Logger:
    """
    Return a named logger configured for console and file output.

    Subsequent calls with the same name reuse the existing logger
    to avoid duplicate handlers.

    Args:
        name: Logger name, typically ``__name__`` of the calling module.

    Returns:
        A configured ``logging.Logger`` instance.
    """
    if name in _LOGGERS:
        return _LOGGERS[name]

    settings = get_settings()
    log_dir: Path = settings.logs_path
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "app.log"

    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, settings.log_level.upper(), logging.INFO))
    logger.propagate = False

    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.DEBUG)
    console_handler.setFormatter(formatter)

    # File handler
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)

    if not logger.handlers:
        logger.addHandler(console_handler)
        logger.addHandler(file_handler)

    _LOGGERS[name] = logger
    return logger
