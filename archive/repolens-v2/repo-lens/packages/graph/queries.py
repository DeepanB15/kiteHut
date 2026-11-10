from sqlalchemy import and_, or_, text
from sqlalchemy.orm import Session
from typing import List, Dict, Any, Optional, Set


class GraphQueryEngine:
    """Bounded graph traversal with evidence tracking."""

    def __init__(self, db_session: Session, max_depth: int = 3):
        self.db = db_session
        self.max_depth = max_depth

    def find_symbol(self, repo_id: str, name: str) -> List[Dict]:
        from app.models import Symbol
        results = self.db.query(Symbol).filter(
            Symbol.repository_id == repo_id,
            Symbol.name == name,
        ).all()
        return [{"id": r.id, "name": r.name, "type": r.symbol_type, "file": r.file_path, "lines": f"{r.line_start}-{r.line_end}"} for r in results]

    def callers_of(self, repo_id: str, symbol_id: str, depth: int = 1) -> List[Dict]:
        from app.models import CallRelationship
        if depth > self.max_depth:
            return []
        results = self.db.query(CallRelationship).filter(
            CallRelationship.repository_id == repo_id,
            CallRelationship.callee_symbol_id == symbol_id,
        ).all()
        return [{"caller_id": r.callers_symbol_id, "line_context": r.line_context} for r in results]

    def callees_of(self, repo_id: str, symbol_id: str, depth: int = 1) -> List[Dict]:
        from app.models import CallRelationship
        if depth > self.max_depth:
            return []
        results = self.db.query(CallRelationship).filter(
            CallRelationship.repository_id == repo_id,
            CallRelationship.callers_symbol_id == symbol_id,
        ).all()
        return [{"callee_id": r.callee_symbol_id, "line_context": r.line_context} for r in results]

    def affected_files(self, repo_id: str, symbol_id: str, max_depth: int = 3) -> Set[str]:
        # Bounded traversal: find dependents (callers + dependents) and collect file paths
        if max_depth > self.max_depth:
            max_depth = self.max_depth
        files = set()
        visited = {symbol_id}
        front = [symbol_id]

        for _ in range(max_depth):
            next_front = []
            for sid in front:
                from app.models import Symbol, DependencyRelationship, CallRelationship
                # Dependents (things that depend on this)
                deps = self.db.query(DependencyRelationship).filter(
                    DependencyRelationship.repository_id == repo_id,
                    DependencyRelationship.depender_symbol_id == sid,
                ).all()
                for d in deps:
                    if d.dependent_symbol_id not in visited:
                        visited.add(d.dependent_symbol_id)
                        next_front.append(d.dependent_symbol_id)

                # Callers
                calls = self.db.query(CallRelationship).filter(
                    CallRelationship.repository_id == repo_id,
                    CallRelationship.callee_symbol_id == sid,
                ).all()
                for c in calls:
                    if c.callers_symbol_id not in visited:
                        visited.add(c.callers_symbol_id)
                        next_front.append(c.callers_symbol_id)

            front = next_front

        # Collect file paths for all visited symbols
        from app.models import Symbol
        for sid in visited:
            sym = self.db.query(Symbol).filter(Symbol.id == sid, Symbol.repository_id == repo_id).first()
            if sym:
                files.add(sym.file_path)
        return files
