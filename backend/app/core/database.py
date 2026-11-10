"""
Database Engine & Session.

Provides SQLAlchemy engine, session factory, and dependency injection.
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase

from app.core.config import settings


# Create engine
# SQLite needs check_same_thread=False and a busy timeout
# (background job threads write to the same file)
connect_args = {}
if settings.DATABASE_URL.startswith("sqlite"):
    connect_args["check_same_thread"] = False
    connect_args["timeout"] = 30

engine = create_engine(
    settings.DATABASE_URL,
    connect_args=connect_args,
    echo=False,
)

# Session factory
# expire_on_commit=False keeps attributes readable on detached instances
# (used by job_service, which returns job objects after closing the session)
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine,
    expire_on_commit=False,
)


# Base class for all models
class Base(DeclarativeBase):
    pass


def get_db():
    """
    FastAPI dependency: yields a database session.
    Ensures the session is closed after use.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _ensure_sqlite_columns() -> None:
    """
    Lightweight column migration for existing SQLite databases.

    New nullable columns added after a table was first created are not
    picked up by create_all(); add them here guarded by a PRAGMA check.
    """
    if not settings.DATABASE_URL.startswith("sqlite"):
        return

    from sqlalchemy import inspect, text

    inspector = inspect(engine)
    try:
        job_columns = {c["name"] for c in inspector.get_columns("analysis_jobs")}
    except Exception:
        return  # table does not exist yet (create_all handles it)

    additions = {
        "job_type": "VARCHAR(20) DEFAULT 'REPOSITORY'",
        "pull_number": "INTEGER",
        "pr_analysis_id": "INTEGER",
    }
    with engine.begin() as connection:
        for column, definition in additions.items():
            if column not in job_columns:
                connection.execute(text(
                    f"ALTER TABLE analysis_jobs ADD COLUMN {column} {definition}"
                ))

    # Phase 9 quality gate / status check columns on pr_analyses
    try:
        pr_columns = {c["name"] for c in inspector.get_columns("pr_analyses")}
    except Exception:
        return  # table does not exist yet (create_all handles it)

    pr_additions = {
        "gate_result": "VARCHAR(10)",
        "gate_reasons": "TEXT",
        "status_check_posted": "BOOLEAN DEFAULT 0",
    }
    with engine.begin() as connection:
        for column, definition in pr_additions.items():
            if column not in pr_columns:
                connection.execute(text(
                    f"ALTER TABLE pr_analyses ADD COLUMN {column} {definition}"
                ))

    # Phase 10 additions
    phase10_tables = {
        "findings": {
            "status": "VARCHAR(20) DEFAULT 'OPEN'",
            "status_note": "TEXT",
            "status_updated_at": "DATETIME",
        },
        "pr_findings": {
            "status": "VARCHAR(20) DEFAULT 'OPEN'",
            "status_note": "TEXT",
        },
        "analysis_runs": {
            "mode": "VARCHAR(20) DEFAULT 'balanced'",
            "enabled_agents": "TEXT",
        },
    }
    for table, columns in phase10_tables.items():
        try:
            existing = {c["name"] for c in inspector.get_columns(table)}
        except Exception:
            continue
        with engine.begin() as connection:
            for column, definition in columns.items():
                if column not in existing:
                    connection.execute(text(
                        f"ALTER TABLE {table} ADD COLUMN {column} {definition}"
                    ))


def init_db():
    """Create all tables (used in development)."""
    Base.metadata.create_all(bind=engine)
    _ensure_sqlite_columns()
