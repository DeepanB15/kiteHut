"""
Repository Structure Inspector for RepoLens Context Engine.

Scans the filesystem, computes language statistics, categorizes directories,
and inventories critical manifest files while respecting standard ignore lists.
"""

from collections import Counter
from dataclasses import field
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Set
from pydantic import BaseModel, Field


IGNORE_DIRECTORIES: Set[str] = {
    ".git",
    "node_modules",
    ".venv",
    "venv",
    "__pycache__",
    ".next",
    "dist",
    "build",
    "coverage",
    ".idea",
    ".vscode",
    ".pytest_cache",
    ".ruff_cache",
    ".mypy_cache",
    "workspace",
    ".cache",
    "tmp",
}

LANGUAGE_EXTENSIONS: Dict[str, str] = {
    ".py": "Python",
    ".js": "JavaScript",
    ".jsx": "JavaScript",
    ".ts": "TypeScript",
    ".tsx": "TypeScript",
    ".java": "Java",
    ".kt": "Kotlin",
    ".go": "Go",
    ".rs": "Rust",
    ".cpp": "C++",
    ".c": "C",
    ".cs": "C#",
    ".php": "PHP",
    ".rb": "Ruby",
    ".swift": "Swift",
    ".html": "HTML",
    ".css": "CSS",
    ".scss": "SCSS",
    ".sql": "SQL",
    ".sh": "Shell",
    ".bash": "Shell",
    ".json": "JSON",
    ".yaml": "YAML",
    ".yml": "YAML",
    ".toml": "TOML",
    ".md": "Markdown",
    ".proto": "Protobuf",
    ".graphql": "GraphQL",
}

DIRECTORY_ROLES: Dict[str, str] = {
    "src": "source",
    "app": "source",
    "lib": "source",
    "backend": "backend",
    "frontend": "frontend",
    "web": "frontend",
    "client": "frontend",
    "server": "backend",
    "api": "api_layer",
    "routes": "api_layer",
    "controllers": "api_layer",
    "models": "data_models",
    "services": "business_logic",
    "views": "presentation",
    "components": "ui_components",
    "tests": "testing",
    "test": "testing",
    "docs": "documentation",
    "config": "configuration",
    "scripts": "tooling",
    "deploy": "infrastructure",
    "infra": "infrastructure",
}


class FileInfo(BaseModel):
    relative_path: str
    extension: str
    language: Optional[str] = None
    line_count: int = 0
    size_bytes: int = 0
    is_manifest: bool = False


class DirectoryStats(BaseModel):
    relative_path: str
    role: str = "general"
    file_count: int = 0
    line_count: int = 0
    primary_language: Optional[str] = None


class RepoStructure(BaseModel):
    root_path: str
    total_files: int = 0
    total_lines: int = 0
    languages: Dict[str, int] = Field(default_factory=dict)
    primary_language: str = "Unknown"
    manifest_files: List[str] = Field(default_factory=list)
    directories: List[DirectoryStats] = Field(default_factory=list)
    file_inventory: List[FileInfo] = Field(default_factory=list)


class RepoInspector:
    """Inspects repository filesystem layout and code statistics."""

    def __init__(self, root_path: str, max_files: int = 10000):
        self.root_path = Path(root_path).resolve()
        self.max_files = max_files

    def is_ignored(self, path: Path) -> bool:
        """Check if a path contains any ignored directory segments."""
        for part in path.parts:
            if part in IGNORE_DIRECTORIES or part.startswith(".git"):
                return True
        return False

    def inspect(self) -> RepoStructure:
        """Scan repository and return structured analysis."""
        if not self.root_path.exists():
            raise FileNotFoundError(f"Repository path does not exist: {self.root_path}")

        files: List[FileInfo] = []
        lang_lines: Counter = Counter()
        dir_map: Dict[str, Dict[str, Any]] = {}
        manifests: List[str] = []

        total_lines = 0

        for current_root, dirs, filenames in os.walk(self.root_path):
            # Prune ignored directories in-place for fast traversal
            dirs[:] = [d for d in dirs if d not in IGNORE_DIRECTORIES and not d.startswith(".")]

            root_p = Path(current_root)
            if self.is_ignored(root_p.relative_to(self.root_path)):
                continue

            for fname in filenames:
                if len(files) >= self.max_files:
                    break

                file_p = root_p / fname
                try:
                    rel_p = str(file_p.relative_to(self.root_path)).replace("\\", "/")
                except ValueError:
                    continue

                ext = file_p.suffix.lower()
                lang = LANGUAGE_EXTENSIONS.get(ext)

                # Compute line count and file size
                lines = 0
                size = 0
                try:
                    size = file_p.stat().st_size
                    # Only read text files
                    if size < 5 * 1024 * 1024:  # < 5MB
                        with open(file_p, "r", encoding="utf-8", errors="ignore") as f:
                            lines = sum(1 for _ in f)
                except Exception:
                    lines = 0

                is_manifest = fname.lower() in {
                    "readme.md",
                    "package.json",
                    "package-lock.json",
                    "pyproject.toml",
                    "requirements.txt",
                    "setup.py",
                    "dockerfile",
                    "docker-compose.yml",
                    "docker-compose.yaml",
                    "tsconfig.json",
                    ".env.example",
                    "cargo.toml",
                    "pom.xml",
                    "build.gradle",
                    "go.mod",
                }

                if is_manifest:
                    manifests.append(rel_p)

                finfo = FileInfo(
                    relative_path=rel_p,
                    extension=ext,
                    language=lang,
                    line_count=lines,
                    size_bytes=size,
                    is_manifest=is_manifest,
                )
                files.append(finfo)

                if lang:
                    lang_lines[lang] += lines

                total_lines += lines

                # Track directory stats
                parent_dir = str(root_p.relative_to(self.root_path)).replace("\\", "/")
                if parent_dir == ".":
                    parent_dir = "root"

                if parent_dir not in dir_map:
                    top_segment = parent_dir.split("/")[0]
                    role = DIRECTORY_ROLES.get(top_segment.lower(), "general")
                    dir_map[parent_dir] = {
                        "relative_path": parent_dir,
                        "role": role,
                        "file_count": 0,
                        "line_count": 0,
                        "lang_counter": Counter(),
                    }

                dir_map[parent_dir]["file_count"] += 1
                dir_map[parent_dir]["line_count"] += lines
                if lang:
                    dir_map[parent_dir]["lang_counter"][lang] += lines

        # Assemble directories
        directories: List[DirectoryStats] = []
        for dpath, dinfo in sorted(dir_map.items()):
            primary_dir_lang = dinfo["lang_counter"].most_common(1)
            directories.append(
                DirectoryStats(
                    relative_path=dinfo["relative_path"],
                    role=dinfo["role"],
                    file_count=dinfo["file_count"],
                    line_count=dinfo["line_count"],
                    primary_language=primary_dir_lang[0][0] if primary_dir_lang else None,
                )
            )

        primary_lang = lang_lines.most_common(1)

        return RepoStructure(
            root_path=str(self.root_path),
            total_files=len(files),
            total_lines=total_lines,
            languages=dict(lang_lines),
            primary_language=primary_lang[0][0] if primary_lang else "Unknown",
            manifest_files=sorted(manifests),
            directories=directories,
            file_inventory=files,
        )
