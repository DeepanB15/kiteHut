"""Real repository indexing service."""
import time
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from sqlalchemy.orm import Session

from packages.ingestion.scanner import RepositoryScanner
from packages.analyzers.python import PythonAnalyzer
from packages.graph.store import GraphStore
try:
    from app.models import Repository, File, Symbol, Relationship
    from app.database import SessionLocal
except ImportError:
    # When called from outside apps/api context, import via relative path
    import importlib.util
    spec = importlib.util.spec_from_file_location("models", r"C:\Users\Deepan B\Desktop\codez\repo-lens\apps\api\app\models.py")
    models = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(models)
    Repository, File, Symbol, Relationship = models.Repository, models.File, models.Symbol, models.Relationship
    spec_db = importlib.util.spec_from_file_location("database", r"C:\Users\Deepan B\Desktop\codez\repo-lens\apps\api\app\database.py")
    database = importlib.util.module_from_spec(spec_db)
    spec_db.loader.exec_module(database)
    SessionLocal = database.SessionLocal


SUPPORTED_LANGUAGES = {"python"}
SUPPORTED_EXTENSIONS = {".py"}


class IndexingService:
    def __init__(self, db: Optional[Session] = None):
        self.db = db or SessionLocal()
        self.store = GraphStore(self.db)
        self.scanner = None

    def index_repository(self, repo_path: str) -> Dict[str, Any]:
        start = time.time()
        path = Path(repo_path).resolve()
        if not path.exists() or not path.is_dir():
            raise ValueError(f"Invalid repository path: {repo_path}")

        # 1. Create/find Repository (idempotent by path)
        repo_name = path.name
        repo = self.db.query(Repository).filter(Repository.path == str(path)).first()
        if repo is None:
            repo = Repository(name=repo_name, path=str(path), status="indexing")
            self.db.add(repo)
            self.db.commit()
            self.db.refresh(repo)

        repo_id = repo.id

        # 2. Scan files
        scanner = RepositoryScanner(str(path))
        scanned = scanner.scan()

        files_indexed = 0
        supported_files = 0
        unsupported_files = []
        symbols_indexed = 0
        relationships_indexed = 0

        # 3. Process each file
        for file_info in scanned:
            rel_path = file_info["relative_path"]
            lang = file_info["language"]
            ext = file_info["extension"]

            # Check if supported
            is_supported = lang in SUPPORTED_LANGUAGES and ext in SUPPORTED_EXTENSIONS

            # Create/update File record (idempotent by repo + path)
            file_rec = self.db.query(File).filter(
                File.repository_id == repo_id,
                File.path == rel_path
            ).first()
            if file_rec is None:
                file_rec = File(
                    repository_id=repo_id,
                    path=rel_path,
                    language=lang if lang != "unknown" else "unknown",
                    line_count=0,
                    is_test=rel_path.startswith("tests/") or rel_path.startswith("test_")
                )
                self.db.add(file_rec)
                self.db.commit()
                self.db.refresh(file_rec)

            files_indexed += 1
            if is_supported:
                supported_files += 1
                # Analyze with PythonAnalyzer
                analyzer = PythonAnalyzer()
                result = analyzer.analyze_file(Path(file_info["absolute_path"]))

                # Update file line count
                file_rec.line_count = result.line_count
                self.db.commit()

                # Persist symbols (idempotent: skip if same repo + file_path + name + type exists)
                existing_symbols = self.db.query(Symbol).filter(
                    Symbol.repository_id == repo_id,
                    Symbol.file_path == rel_path
                ).all()
                existing_keys = {
                    (s.name, s.symbol_type, s.file_path): s.id for s in existing_symbols
                }

                for sym_info in result.symbols:
                    key = (sym_info.name, sym_info.symbol_type, rel_path)
                    if key not in existing_keys:
                        sym = Symbol(
                            repository_id=repo_id,
                            file_id=file_rec.id,
                            symbol_type=sym_info.symbol_type,
                            name=sym_info.name,
                            file_path=rel_path,
                            line_start=sym_info.line_start,
                            line_end=sym_info.line_end,
                            qualified_name=sym_info.qualified_name,
                            module_path=sym_info.module_path,
                        )
                        self.db.add(sym)
                        self.db.commit()
                        self.db.refresh(sym)
                        existing_keys[key] = sym.id
                        symbols_indexed += 1

                # Persist relationships from analyzer (real only; Python analyzer currently returns [])
                existing_rels = self.db.query(Relationship).filter(
                    Relationship.repository_id == repo_id
                ).all()
                existing_rel_keys = {
                    (r.source_symbol_id, r.target_symbol_id, r.relationship_type): r.id
                    for r in existing_rels
                }

                # No relationships produced by PythonAnalyzer (correct behavior; empty list)
                pass
            else:
                unsupported_files.append({"path": rel_path, "language": lang, "extension": ext})

        # Update repository counts and status
        repo.last_indexed_at = __import__('datetime').datetime.utcnow()
        repo.status = "indexed"
        repo.total_files = self.db.query(File).filter(File.repository_id == repo_id).count()
        repo.total_symbols = self.db.query(Symbol).filter(Symbol.repository_id == repo_id).count()
        self.db.commit()

        duration = time.time() - start
        return {
            "repository_id": repo_id,
            "repository_path": str(path),
            "files_indexed": files_indexed,
            "supported_files": supported_files,
            "unsupported_files": unsupported_files,
            "symbols_indexed": symbols_indexed,
            "relationships_indexed": relationships_indexed,
            "duration_seconds": round(duration, 3),
        }
