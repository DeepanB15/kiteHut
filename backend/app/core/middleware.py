"""
HTTP Middleware.

RequestContextMiddleware:
    - Assigns a request id (X-Request-ID) per request
    - Logs a structured access line per request
    - Returns the request id in the response header

SecurityMiddleware:
    - Enforces a maximum request body size (413)
    - Simple in-memory per-IP rate limiting (429)
    - Skips health/readiness/docs paths and CORS preflight (OPTIONS)
"""

import logging
import time
import uuid
from collections import defaultdict, deque

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.core.config import settings
from app.core.logging import request_id_var

logger = logging.getLogger("repolens.request")

# Paths exempt from rate limiting / body limits
EXEMPT_PATHS = {
    "/health",
    "/ready",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/",
}


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Add request ids and structured access logging to every request."""

    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        request_id_var.set(request_id)

        start = time.perf_counter()
        response = None
        try:
            response = await call_next(request)
            status_code = response.status_code
        except Exception:
            # Let the exception propagate to FastAPI's exception handlers;
            # still log the access line with the request id.
            status_code = 500
            duration_ms = (time.perf_counter() - start) * 1000
            logger.info(
                "%s %s -> %s (%.1fms)",
                request.method,
                request.url.path,
                status_code,
                duration_ms,
            )
            raise

        duration_ms = (time.perf_counter() - start) * 1000
        logger.info(
            "%s %s -> %s (%.1fms)",
            request.method,
            request.url.path,
            status_code,
            duration_ms,
        )

        response.headers["X-Request-ID"] = request_id
        return response


class SecurityMiddleware(BaseHTTPMiddleware):
    """
    Request hardening: payload size limit and per-IP rate limiting.

    In-memory sliding window; adequate for a single-process deployment.
    """

    def __init__(self, app):
        super().__init__(app)
        self._hits: dict[str, deque] = defaultdict(deque)

    def _is_exempt(self, request: Request) -> bool:
        if request.method == "OPTIONS":
            return True  # CORS preflight
        return request.url.path in EXEMPT_PATHS

    async def dispatch(self, request: Request, call_next):
        # 1. Payload size limit
        if not self._is_exempt(request) and request.method in ("POST", "PUT", "PATCH"):
            content_length = request.headers.get("content-length")
            if content_length and content_length.isdigit():
                if int(content_length) > settings.MAX_REQUEST_BYTES:
                    return JSONResponse(
                        status_code=413,
                        content={
                            "detail": "Request body too large",
                            "max_bytes": settings.MAX_REQUEST_BYTES,
                            "request_id": request_id_var.get(),
                        },
                    )

        # 2. Rate limiting (per IP, sliding 60s window)
        if (
            not self._is_exempt(request)
            and settings.RATE_LIMIT_PER_MINUTE > 0
        ):
            client_ip = request.client.host if request.client else "unknown"
            now = time.monotonic()
            window = self._hits[client_ip]
            while window and now - window[0] > 60:
                window.popleft()
            if len(window) >= settings.RATE_LIMIT_PER_MINUTE:
                return JSONResponse(
                    status_code=429,
                    content={
                        "detail": "Rate limit exceeded. Please try again later.",
                        "request_id": request_id_var.get(),
                    },
                )
            window.append(now)

        return await call_next(request)