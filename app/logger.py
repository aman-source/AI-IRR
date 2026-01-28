"""Structured logging setup for IRR Automation."""

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from app.config import LoggingConfig


class JSONFormatter(logging.Formatter):
    """JSON log formatter for structured logging."""

    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON."""
        log_entry: Dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Add context if present
        if hasattr(record, 'context') and record.context:
            log_entry["context"] = record.context

        # Add exception info if present
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_entry)


class TextFormatter(logging.Formatter):
    """Human-readable text formatter."""

    def __init__(self):
        super().__init__(
            fmt="[%(asctime)s] %(levelname)s %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )

    def format(self, record: logging.LogRecord) -> str:
        """Format log record as human-readable text."""
        base = super().format(record)

        # Append context if present
        if hasattr(record, 'context') and record.context:
            context_str = " | ".join(f"{k}={v}" for k, v in record.context.items())
            base = f"{base} [{context_str}]"

        return base


class ContextLogger(logging.LoggerAdapter):
    """Logger adapter that supports context injection."""

    def process(self, msg: str, kwargs: Dict[str, Any]):
        """Process log message with context."""
        # Merge adapter's extra with call-time extra
        extra = kwargs.get('extra', {})
        if self.extra:
            extra = {**self.extra, **extra}

        # Extract context for structured logging
        context = extra.pop('context', None)
        if context:
            extra['context'] = context

        kwargs['extra'] = extra
        return msg, kwargs


def setup_logging(config: LoggingConfig) -> logging.Logger:
    """
    Set up logging based on configuration.

    Args:
        config: Logging configuration.

    Returns:
        Configured root logger.
    """
    # Get numeric level
    level = getattr(logging, config.level.upper(), logging.INFO)

    # Create root logger for the app
    logger = logging.getLogger("app")
    logger.setLevel(level)

    # Clear any existing handlers
    logger.handlers.clear()

    # Choose formatter based on config
    if config.format.lower() == "json":
        formatter = JSONFormatter()
    else:
        formatter = TextFormatter()

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # File handler if configured
    if config.file:
        file_path = Path(config.file)
        file_path.parent.mkdir(parents=True, exist_ok=True)

        file_handler = logging.FileHandler(file_path, encoding='utf-8')
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    # Prevent propagation to root logger
    logger.propagate = False

    return logger


def get_logger(name: str, context: Optional[Dict[str, Any]] = None) -> ContextLogger:
    """
    Get a logger with optional context.

    Args:
        name: Logger name (usually module name).
        context: Optional context dict to include in all log messages.

    Returns:
        ContextLogger instance.
    """
    base_logger = logging.getLogger(f"app.{name}")
    return ContextLogger(base_logger, context or {})


def log_with_context(
    logger: logging.Logger,
    level: int,
    message: str,
    context: Optional[Dict[str, Any]] = None,
    **kwargs
):
    """
    Log a message with context data.

    Args:
        logger: Logger instance.
        level: Log level (e.g., logging.INFO).
        message: Log message.
        context: Context dict to include in structured log.
        **kwargs: Additional keyword arguments for logging.
    """
    extra = kwargs.pop('extra', {})
    if context:
        extra['context'] = context
    logger.log(level, message, extra=extra, **kwargs)
