"""Minimal local logging with no telemetry or personal-payload logging."""

from __future__ import annotations

import json
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return json.dumps(
            {
                "level": record.levelname,
                "logger": record.name,
                "message": record.getMessage(),
            },
            separators=(",", ":"),
        )


def configure_logging(log_path: Path) -> None:
    """Configure stderr and rotating user-local logs exactly once per process."""

    log_path.parent.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("ion")
    # Uvicorn's test/runtime configuration may disable pre-existing named
    # loggers. Reconfiguration must restore Ion's explicit local logger.
    logger.disabled = False
    logger.propagate = False
    logger.setLevel(logging.INFO)
    if logger.handlers:
        return

    formatter = JsonFormatter()
    stderr_handler = logging.StreamHandler()
    file_handler = RotatingFileHandler(log_path, maxBytes=1_000_000, backupCount=3)
    for handler in (stderr_handler, file_handler):
        handler.setFormatter(formatter)
        logger.addHandler(handler)
