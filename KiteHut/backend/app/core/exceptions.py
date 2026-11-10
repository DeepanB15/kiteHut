"""
Centralized Error Handling.

Registers FastAPI exception handlers that return safe, consistent JSON
error responses (no stack traces leaked to clients).

Stack traces and error context are logged server-side only, tagged with
the request id so they can be correlated with client reports.
"""

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.core.logging import request_id_var

logger = logging.getLogger("repolens.errors")


class RepoLensError(Exception):
    """Base class for all RepoLens application errors."""


class RepositoryNotAllowedError(RepoLensError):
    """Raised when a repository URL points to a non-allowed host."""


class AnalysisJobNotFoundError(RepoLensError):
    """Raised when an analysis job id does not exist."""


def register_exception_handlers(app: FastAPI) -> None:
    """Attach safe exception handlers to the FastAPI app."""

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        """Return a sanitized 422 response for invalid request payloads."""
        errors = []
        for error in exc.errors()[:5]:
            loc = ".".join(str(part) for part in error.get("loc", []) if part != "body")
            errors.append({"field": loc, "message": error.get("msg", "Invalid value")})

        return JSONResponse(
            status_code=422,
            content={
                "detail": "Invalid request payload",
                "errors": errors,
                "request_id": request_id_var.get(),
            },
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(
        request: Request, exc: Exception
    ) -> JSONResponse:
        """Log the full traceback server-side, return a safe 500 response."""
        request_id = request_id_var.get()
        logger.exception(
            "Unhandled error on %s %s (request_id=%s)",
            request.method,
            request.url.path,
            request_id,
        )
        return JSONResponse(
            status_code=500,
            content={
                "detail": "Internal server error",
                "request_id": request_id,
            },
        )