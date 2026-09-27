"""Application logging: console for users, rotating file for debugging.

Normal runs stay quiet; warnings and errors are mirrored to ``app.log``
(with tracebacks) so field issues can be diagnosed after the fact.
"""
from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

_LOG_PATH = Path(__file__).resolve().parents[1] / "app.log"
_logger: logging.Logger | None = None


def get_logger(name: str = "gesture_studio") -> logging.Logger:
    """Return the shared logger (configured on first call)."""
    global _logger
    if _logger is not None:
        return _logger
    _logger = logging.getLogger(name)
    _logger.setLevel(logging.DEBUG)
    console = logging.StreamHandler(sys.stderr)
    console.setLevel(logging.WARNING)
    console.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
    logfile = RotatingFileHandler(str(_LOG_PATH), maxBytes=256_000,
                                  backupCount=2, encoding="utf-8")
    logfile.setLevel(logging.DEBUG)
    logfile.setFormatter(logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s: %(message)s"))
    _logger.addHandler(console)
    _logger.addHandler(logfile)
    _logger.propagate = False
    return _logger


def log_exception(message: str, exc: BaseException) -> None:
    """Log ``message`` plus the traceback of ``exc`` at ERROR level."""
    get_logger().error("%s: %r", message, exc, exc_info=exc)
