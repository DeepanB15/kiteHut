"""
Application Configuration.

Loads settings from environment variables with optional .env file support.

Environments (ENVIRONMENT variable):
    development  -> loads .env then .env.development (if present)
    production   -> loads .env then .env.production   (if present)
    testing      -> loads .env then .env.testing       (if present)

Rule: never hardcode database credentials, API keys, secrets, or
production URLs. Everything must come from environment variables.
"""

import os
from pathlib import Path

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent.parent.parent  # backend/


def _load_env_files() -> None:
    """Load .env, then the environment-specific override file if present."""
    # Base .env (optional, does not override real environment variables)
    load_dotenv(BASE_DIR / ".env")

    environment = os.getenv("ENVIRONMENT", "development")
    env_file = BASE_DIR / f".env.{environment}"
    if env_file.exists():
        load_dotenv(env_file, override=True)


_load_env_files()


class Settings:
    """Application settings, sourced from environment variables."""

    # ------------------------------------------------------------
    # Environment
    # ------------------------------------------------------------
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")

    @property
    def is_production(self) -> bool:
        return self.ENVIRONMENT.lower() == "production"

    @property
    def is_testing(self) -> bool:
        return self.ENVIRONMENT.lower() == "testing"

    # ------------------------------------------------------------
    # Server
    # ------------------------------------------------------------
    API_HOST: str = os.getenv("API_HOST", "0.0.0.0")
    API_PORT: int = int(os.getenv("API_PORT", "8000"))

    # ------------------------------------------------------------
    # Database
    # ------------------------------------------------------------
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL",
        f"sqlite:///{BASE_DIR / 'kitehut.db'}",
    )

    # PostgreSQL (used when DATABASE_URL is not set)
    POSTGRES_USER: str = os.getenv("POSTGRES_USER", "repolens")
    POSTGRES_PASSWORD: str = os.getenv("POSTGRES_PASSWORD", "repolens_password")
    POSTGRES_DB: str = os.getenv("POSTGRES_DB", "repolens_db")
    POSTGRES_HOST: str = os.getenv("POSTGRES_HOST", "localhost")
    POSTGRES_PORT: str = os.getenv("POSTGRES_PORT", "5432")

    # ------------------------------------------------------------
    # LLM
    # ------------------------------------------------------------
    LLM_PROVIDER: str = os.getenv("LLM_PROVIDER", "ollama")
    OLLAMA_BASE_URL: str = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    OLLAMA_MODEL: str = os.getenv("OLLAMA_MODEL", "qwen3:4b")

    # ------------------------------------------------------------
    # CORS — comma-separated list of allowed origins
    # ------------------------------------------------------------
    CORS_ORIGINS: str = os.getenv(
        "CORS_ORIGINS",
        "http://localhost:5173,http://localhost:8080",
    )

    @property
    def cors_origins(self) -> list[str]:
        """Parse the comma-separated CORS origins into a list."""
        return [
            origin.strip()
            for origin in self.CORS_ORIGINS.split(",")
            if origin.strip()
        ]

    # ------------------------------------------------------------
    # Security
    # ------------------------------------------------------------
    # Comma-separated list of allowed repository hosts (e.g. github.com)
    ALLOWED_REPOSITORY_HOSTS: str = os.getenv(
        "ALLOWED_REPOSITORY_HOSTS", "github.com"
    )

    @property
    def allowed_repository_hosts(self) -> list[str]:
        return [
            host.strip().lower()
            for host in self.ALLOWED_REPOSITORY_HOSTS.split(",")
            if host.strip()
        ]

    # Maximum accepted request body size in bytes (default 1 MB)
    MAX_REQUEST_BYTES: int = int(os.getenv("MAX_REQUEST_BYTES", "1048576"))

    # Simple per-IP rate limit (requests per minute). 0 disables limiting.
    RATE_LIMIT_PER_MINUTE: int = int(os.getenv("RATE_LIMIT_PER_MINUTE", "120"))

    # ------------------------------------------------------------
    # GitHub Integration (Phase 9)
    # ------------------------------------------------------------
    # Personal Access Token (optional — public repos work without it).
    # Required for private repos, PR comment posting, and higher rate limits.
    GITHUB_TOKEN: str = os.getenv("GITHUB_TOKEN", "")
    GITHUB_API_URL: str = os.getenv("GITHUB_API_URL", "https://api.github.com")
    # Shared secret for verifying GitHub webhook signatures (X-Hub-Signature-256)
    GITHUB_WEBHOOK_SECRET: str = os.getenv("GITHUB_WEBHOOK_SECRET", "")
    # Max changed files scanned per PR analysis (large PRs are capped)
    PR_MAX_CHANGED_FILES: int = int(os.getenv("PR_MAX_CHANGED_FILES", "100"))
    # Post a summary comment back to the PR when analysis completes
    PR_POST_COMMENT: bool = os.getenv("PR_POST_COMMENT", "true").lower() in ("true", "1", "yes")
    # Post a commit status check on the PR's head commit after analysis
    PR_POST_STATUS_CHECK: bool = os.getenv(
        "PR_POST_STATUS_CHECK", "true"
    ).lower() in ("true", "1", "yes")
    # Commit status check context shown in the GitHub PR checks UI
    QUALITY_GATE_CONTEXT: str = os.getenv("QUALITY_GATE_CONTEXT", "RepoLens/Quality-Gate")

    # ------------------------------------------------------------
    # Quality Gate (Phase 9)
    # ------------------------------------------------------------
    # A PR analysis fails the gate when any of these limits are exceeded.
    # Defaults: 0 critical, 0 security findings, min health 60.
    QUALITY_GATE_CRITICAL_LIMIT: int = int(os.getenv("QUALITY_GATE_CRITICAL_LIMIT", "0"))
    QUALITY_GATE_SECURITY_LIMIT: int = int(os.getenv("QUALITY_GATE_SECURITY_LIMIT", "0"))
    QUALITY_GATE_MIN_HEALTH: float = float(os.getenv("QUALITY_GATE_MIN_HEALTH", "60"))

    @property
    def github_token(self) -> str | None:
        """GitHub token or None when not configured."""
        return self.GITHUB_TOKEN or None

    # ------------------------------------------------------------
    # Notifications (Phase 10)
    # ------------------------------------------------------------
    # Optional webhook URL receiving notification JSON (Slack/Discord/custom)
    NOTIFICATION_WEBHOOK_URL: str = os.getenv("NOTIFICATION_WEBHOOK_URL", "")

    # ------------------------------------------------------------
    # Logging
    # ------------------------------------------------------------
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "info").upper()

    @property
    def is_postgres(self) -> bool:
        """Check if using PostgreSQL."""
        return self.DATABASE_URL.startswith("postgresql")

    @property
    def async_database_url(self) -> str:
        """Get async database URL for SQLAlchemy."""
        if self.DATABASE_URL.startswith("postgresql"):
            return self.DATABASE_URL.replace("postgresql://", "postgresql+psycopg://")
        return self.DATABASE_URL.replace("sqlite://", "sqlite+aiosqlite://")


settings = Settings()