"""
Structured Logging.

Provides:
    - A configured root logger with structured, request-scoped output.
    - A request_id context variable used by the request middleware.
    - A small helper to get named loggers consistently.

Log format includes: timestamp, level, logger name, request_id, message.
"""

import logging
import sys
from contextvars import ContextVar

from app.core.config import settings


# Per-request request id, set by RequestContextMiddleware
request_id_var: ContextVar[str] = ContextVar("request_id", default="-")


class RequestIDFilter(logging.Filter):
    """Inject the current request_id into every log record."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get()
        return True


def get_logger(name: str) -> logging.Logger:
    """Get a named logger (root logger is pre-configured by setup_logging)."""
    return logging.getLogger(name)


def setup_logging() -> None:
    """Configure the root logger with structured, request-aware output."""
    level = getattr(logging, settings.LOG_LEVEL, logging.INFO)

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-7s | %(name)s | "
        "request_id=%(request_id)s | %(message)s"
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)
    handler.addFilter(RequestIDFilter())

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)

    # Keep uvicorn's own loggers visible through the same handler
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        uvicorn_logger = logging.getLogger(name)
        uvicorn_logger.handlers = [handler]
        uvicorn_logger.propagate = False


# Configure once at import time (idempotent: replaces handlers on reload)
setup_logging()