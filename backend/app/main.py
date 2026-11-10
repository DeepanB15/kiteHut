"""
RepoLens API — Application Entry Point.

Phase 8 (production readiness):
    - Environment-driven configuration (app.core.config)
    - Structured logging with request ids (app.core.logging / middleware)
    - CORS restricted to configured origins
    - Request hardening: payload limits + per-IP rate limiting
    - Safe exception handlers (no stack traces leaked)
    - Liveness (/health) and readiness (/ready) endpoints
"""

import logging
from urllib.parse import urljoin

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.api.routes import router as api_router
from app.api.history_routes import router as history_router
from app.api.action_routes import router as action_router
from app.api.github_routes import router as github_router
from app.api.product_routes import router as product_router
from app.api.agent_routes import router as agent_router
from app.api.monitoring_routes import router as monitoring_router
from app.core.config import settings
from app.core.database import SessionLocal, init_db
from app.core.exceptions import register_exception_handlers
from app.core.logging import setup_logging
from app.core.middleware import RequestContextMiddleware, SecurityMiddleware

logger = logging.getLogger("repolens.main")

# Structured logging (idempotent) + tables (development mode)
setup_logging()
init_db()

app = FastAPI(
    title="RepoLens API",
    description="Agentic Repository Intelligence and Code Review System",
    version="1.0.0",
)

# ------------------------------------------------------------
# Middleware (last added = outermost)
# ------------------------------------------------------------
app.add_middleware(SecurityMiddleware)
app.add_middleware(RequestContextMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Safe JSON error responses
register_exception_handlers(app)


# ============================================================
# Root / Liveness / Readiness
# ============================================================

@app.get("/")
def root():
    return {
        "message": "Welcome to RepoLens API",
        "status": "running",
        "version": "1.0.0",
        "phases": "1-10 complete",
        "environment": settings.ENVIRONMENT,
        "docs": "/docs",
        "health": "/health",
        "readiness": "/ready",
    }


@app.get("/health")
def health_check():
    """Liveness probe: the process is up."""
    return {
        "status": "healthy",
        "version": "1.0.0",
    }


@app.get("/ready")
def readiness_check():
    """
    Readiness probe: verifies core dependencies.

    - database: required (SELECT 1)
    - ollama: optional (reported, but does not fail readiness)
    """
    services: dict[str, str] = {}

    # Database check (required)
    db_status = "unhealthy"
    try:
        db = SessionLocal()
        try:
            db.execute(text("SELECT 1"))
            db_status = "healthy"
        finally:
            db.close()
    except Exception as error:  # noqa: BLE001
        logger.error("Readiness: database check failed: %s", error)
    services["database"] = db_status

    # Ollama check (optional)
    ollama_status = "unavailable"
    try:
        tags_url = urljoin(settings.OLLAMA_BASE_URL.rstrip("/") + "/", "api/tags")
        response = httpx.get(tags_url, timeout=3.0)
        ollama_status = "healthy" if response.status_code == 200 else "unavailable"
    except Exception:  # noqa: BLE001 - Ollama is optional
        ollama_status = "unavailable"
    services["ollama"] = ollama_status

    if db_status != "healthy":
        return {
            "status": "not_ready",
            "services": services,
        }

    # Database healthy; Ollama optional -> degraded when missing
    return {
        "status": "ready" if ollama_status == "healthy" else "degraded",
        "services": services,
    }


# ============================================================
# Routers
# ============================================================

app.include_router(api_router)
app.include_router(history_router)
app.include_router(action_router)
app.include_router(github_router)
app.include_router(product_router)
app.include_router(agent_router)
app.include_router(monitoring_router)