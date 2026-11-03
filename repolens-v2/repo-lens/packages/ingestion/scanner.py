"""Ingestion service — scanner + indexer."""
import os
import hashlib
from pathlib import Path
from typing import List, Dict, Optional


IGNORE_DIRS = {
    ".git", "__pycache__", ".venv", "venv", "dist", "build",
    ".next", "coverage", ".pytest_cache", ".idea", ".vscode",
    "node_modules",
}

IGNORE_FILES = {".env", ".env.local"}


class RepositoryScanner:
    def __init__(self, repo_path: str):
        self.repo_path = Path(repo_path).resolve()
        if not self.repo_path.exists():
            raise ValueError(f"Repository path does not exist: {repo_path}")
        if not self.repo_path.is_dir():
            raise ValueError(f"Path is not a directory: {repo_path}")

    def scan(self) -> List[Dict]:
        results = []
        for root, dirs, files in os.walk(str(self.repo_path), topdown=True):
            dirs[:] = [d for d in dirs if d not in IGNORE_DIRS]
            for f in files:
                if f in IGNORE_FILES:
                    continue
                full = Path(root) / f
                try:
                    stat = full.stat()
                    rel = full.relative_to(self.repo_path).as_posix()
                    results.append({
                        "relative_path": rel,
                        "absolute_path": str(full),
                        "file_name": f,
                        "extension": full.suffix,
                        "language": "python" if full.suffix in {".py"} else ("javascript" if full.suffix in {".js", ".jsx", ".mjs"} else ("typescript" if full.suffix in {".ts", ".tsx"} else "unknown")),
                        "size_bytes": stat.st_size,
                        "sha256": hashlib.sha256(full.read_bytes()).hexdigest()[:16],
                    })
                except Exception:
                    continue
        return results
