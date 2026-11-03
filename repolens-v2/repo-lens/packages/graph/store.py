from sqlalchemy import text, and_
from sqlalchemy.orm import Session
from typing import List, Dict, Any, Optional
from dataclasses import dataclass


@dataclass
class Node:
    id: str
    symbol_type: str
    name: str
    file_path: str
    line_start: int
    line_end: int


@dataclass
class Edge:
    source_symbol_id: str
    target_symbol_id: str
    relationship_type: str


class GraphStore:
    def __init__(self, db_session: Session):
        self.db = db_session

    def save_symbol(self, symbol: Dict[str, Any]) -> str:
        # Insert or update symbol in DB; returns symbol id
        from app.models import Symbol
        s = Symbol(
            repository_id=symbol.get("repository_id", ""),
            symbol_type=symbol["symbol_type"],
            name=symbol["name"],
            file_path=symbol["file_path"],
            line_start=symbol.get("line_start"),
            line_end=symbol.get("line_end"),
            qualified_name=symbol.get("qualified_name"),
            module_path=symbol.get("module_path"),
        )
        self.db.add(s)
        self.db.commit()
        return s.id

    def build_relationship(self, repo_id: str, source_id: str, target_id: str, rel_type: str, evidence: Optional[Dict] = None):
        from app.models import Relationship
        r = Relationship(
            repository_id=repo_id,
            source_symbol_id=source_id,
            target_symbol_id=target_id,
            relationship_type=rel_type,
            evidence_ref=evidence,
        )
        self.db.add(r)
        self.db.commit()
        return r.id
