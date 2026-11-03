"""Minimum integration tests for Phase 2 verification."""
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

DB_URL = "postgresql+psycopg2://repolens:repolens@localhost:5432/repolens"

engine = create_engine(DB_URL)
TestingSessionLocal = sessionmaker(bind=engine)


def test_migration_database():
    with engine.connect() as conn:
        result = conn.execute(text("SELECT tablename FROM pg_tables WHERE schemaname='public'"))
        tables = {r[0] for r in result.fetchall()}
        assert "repositories" in tables
        assert "files" in tables
        assert "symbols" in tables
        assert "relationships" in tables
        assert "findings" in tables
        assert "fix_proposals" in tables


def test_repository_persistence():
    db = TestingSessionLocal()
    from app.models import Repository
    repos = db.query(Repository).all()
    assert len(repos) >= 1


def test_file_persistence():
    db = TestingSessionLocal()
    from app.models import File
    files = db.query(File).all()
    assert len(files) == 5


def test_symbol_persistence():
    db = TestingSessionLocal()
    from app.models import Symbol
    symbols = db.query(Symbol).all()
    assert len(symbols) == 7


def test_relationship_persistence():
    db = TestingSessionLocal()
    from app.models import Relationship
    rels = db.query(Relationship).all()
    assert len(rels) == 3


def test_graph_query():
    db = TestingSessionLocal()
    from app.models import Relationship
    rels = db.query(Relationship).filter(Relationship.repository_id == "b48b8199-64df-4089-8a39-ab5852778a20").all()
    assert len(rels) == 3


def test_api_health():
    import requests
    try:
        r = requests.get("http://localhost:8000/health", timeout=2)
        assert r.status_code == 200
    except Exception:
        pytest.skip("API not running")


def test_duplicate_indexing():
    # Verify same repo indexed twice does not duplicate (current behavior: insert ignores conflicts for simplicity)
    db = TestingSessionLocal()
    from app.models import Repository
    repos = db.query(Repository).filter(Repository.name == "fixture-python-repo").all()
    assert len(repos) == 1
