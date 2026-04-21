"""Structured logging utilities for persistent JSON logs."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any


class JsonLogFormatter(logging.Formatter):
    """Format logging records as single-line JSON payloads."""

    def format(self, record: logging.LogRecord) -> str:
        base_payload: dict[str, Any] = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        extra_fields = getattr(record, "extra_fields", None)
        if isinstance(extra_fields, dict):
            for key, value in extra_fields.items():
                if key in base_payload:
                    continue
                base_payload[key] = value

        if record.exc_info:
            base_payload["exception"] = self.formatException(record.exc_info)

        return json.dumps(base_payload, default=str)


_LOGGER_CACHE: dict[str, logging.Logger] = {}


def get_structured_logger(name: str = "qpl", log_dir: str = "logs") -> logging.Logger:
    """Return singleton JSON logger writing to console + rotating file."""
    if name in _LOGGER_CACHE:
        return _LOGGER_CACHE[name]

    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    logger.propagate = False

    if logger.handlers:
        _LOGGER_CACHE[name] = logger
        return logger

    Path(log_dir).mkdir(parents=True, exist_ok=True)
    formatter = JsonLogFormatter()

    file_handler = RotatingFileHandler(
        Path(log_dir) / "app.log",
        maxBytes=5_000_000,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)

    logger.addHandler(file_handler)
    logger.addHandler(stream_handler)

    _LOGGER_CACHE[name] = logger
    return logger


def log_event(logger: logging.Logger, level: str, message: str, **fields: Any) -> None:
    """Emit structured log event with dynamic payload."""
    level_normalized = level.lower()
    extra = {"extra_fields": fields}

    if level_normalized == "debug":
        logger.debug(message, extra=extra)
    elif level_normalized == "warning":
        logger.warning(message, extra=extra)
    elif level_normalized == "error":
        logger.error(message, extra=extra)
    elif level_normalized == "critical":
        logger.critical(message, extra=extra)
    else:
        logger.info(message, extra=extra)
