from sqlalchemy.orm import Session
from typing import List, Dict, Any, Set
from .queries import GraphQueryEngine


class ImpactEngine:
    """Calculate blast radius for a symbol change."""

    def __init__(self, db_session: Session):
        self.query = GraphQueryEngine(db_session)

    def analyze(self, repo_id: str, symbol_id: str) -> Dict[str, Any]:
        return {
            "direct_dependents": [],
            "indirect_dependents": [],
            "callers": [],
            "callees": [],
            "related_tests": [],
            "affected_files": [],
            "severity": "LOW",
            "evidence": {},
        }

    def calculate_impact(self, repo_id: str, symbol_id: str) -> Dict[str, Any]:
        result = {
            "symbol_id": symbol_id,
            "direct_dependents": self.query.callers_of(repo_id, symbol_id),
            "indirect_dependents": self.query.callers_of(repo_id, symbol_id, depth=2),
            "callers": self.query.callees_of(repo_id, symbol_id),
            "callees": self.query.callees_of(repo_id, symbol_id, depth=2),
            "affected_files": list(self.query.affected_files(repo_id, symbol_id)),
            "severity": "MEDIUM",
            "evidence": {"source": True},
        }
        # Determine severity by file count and dependency fan-out
        file_count = len(result["affected_files"])
        if file_count >= 8:
            result["severity"] = "HIGH"
        elif file_count >= 3:
            result["severity"] = "MEDIUM"
        else:
            result["severity"] = "LOW"
        return result
