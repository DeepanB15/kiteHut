"""
Context Selector.

Selects only relevant files and content for AI agents.
Prevents sending entire repositories to the LLM.
"""

from pathlib import Path
from typing import List

from app.models.repository_context import RepositoryContext


# Max characters per file content
MAX_FILE_CONTENT_CHARS = 3000

# Max total context characters sent to an agent
MAX_TOTAL_CONTEXT_CHARS = 12000

# Priority file names for context selection
PRIORITY_FILES = {
    # Priority 1: Documentation
    "readme.md": 1,
    "readme": 1,

    # Priority 2: Dependencies & Config
    "requirements.txt": 2,
    "pyproject.toml": 2,
    "package.json": 2,
    "pom.xml": 2,
    "build.gradle": 2,
    "dockerfile": 2,
    "docker-compose.yml": 2,
    "docker-compose.yaml": 2,
    ".env.example": 2,
    ".gitignore": 2,

    # Priority 3: Entry points
    "main.py": 3,
    "app.py": 3,
    "index.js": 3,
    "server.js": 3,
    "manage.py": 3,
    "main.java": 3,
}

# Directories to skip when selecting files
SKIP_DIRS = {
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
    "docs",
    "docs_src",
    "__tests__",
}

# Source file extensions to consider for context
SOURCE_EXTENSIONS = {
    ".py", ".js", ".jsx", ".ts", ".tsx",
    ".java", ".kt", ".go", ".rs",
    ".rb", ".php", ".cs",
}


def _read_file_safely(file_path: Path) -> str:
    """Read a file safely, returning empty string on failure."""

    try:
        content = file_path.read_text(
            encoding="utf-8",
            errors="ignore",
        )
        return content[:MAX_FILE_CONTENT_CHARS]

    except Exception:
        return ""


def _is_skippable(path: Path) -> bool:
    """Check if a path should be skipped."""

    return any(
        part in SKIP_DIRS
        for part in path.parts
    )


def _get_priority(file_path: Path) -> int:
    """Get the priority number for a file (lower = higher priority)."""

    name = file_path.name.lower()
    return PRIORITY_FILES.get(name, 99)


def select_context(
    context: RepositoryContext,
    repository_path: str,
) -> dict:
    """
    Select relevant context for an AI agent.

    Returns a dictionary containing:
    - repository_summary: Basic repo info
    - directory_tree: Top-level directory structure
    - selected_files: List of {path, content} for important files
    - technology_stack: Detected technologies
    """

    repo_path = Path(repository_path)

    # Build directory tree (top 2 levels)
    directory_tree = _build_directory_tree(repo_path)

    # Select and read important files
    selected_files = _select_important_files(
        context, repo_path
    )

    # Select source files if there's room
    source_files = _select_source_files(
        repo_path, selected_files
    )

    selected_files.extend(source_files)

    return {
        "repository_summary": _build_summary(context),
        "directory_tree": directory_tree,
        "selected_files": selected_files,
        "technology_stack": context.technologies,
        "languages": context.languages,
        "structure": {
            "source_directories": context.structure.source_directories,
            "test_directories": context.structure.test_directories,
            "frontend_directories": context.structure.frontend_directories,
            "documentation_directories": context.structure.documentation_directories,
            "application_components": context.structure.application_components,
        },
        "entry_points": context.entry_points,
        "statistics": {
            "total_files": context.statistics.total_files,
            "total_directories": context.statistics.total_directories,
        },
    }


def _build_summary(context: RepositoryContext) -> str:
    """Build a one-line summary of the repository."""

    parts = [
        f"Repository: {context.repository_owner}/{context.repository_name}",
        f"URL: {context.repository_url}",
        f"Files: {context.statistics.total_files}",
        f"Directories: {context.statistics.total_directories}",
    ]

    if context.languages:
        langs = ", ".join(context.languages.keys())
        parts.append(f"Languages: {langs}")

    if context.technologies:
        techs = ", ".join(context.technologies)
        parts.append(f"Technologies: {techs}")

    return " | ".join(parts)


def _build_directory_tree(repo_path: Path) -> str:
    """Build a compact directory tree (2 levels deep)."""

    lines = []

    try:
        entries = sorted(repo_path.iterdir())

        for entry in entries:
            if entry.name.startswith("."):
                continue
            if entry.name in SKIP_DIRS:
                continue

            if entry.is_dir():
                lines.append(f"  {entry.name}/")

                # Show one level of children
                try:
                    children = sorted(entry.iterdir())[:8]
                    for child in children:
                        if child.name.startswith("."):
                            continue
                        if child.name in SKIP_DIRS:
                            continue
                        if child.is_dir():
                            lines.append(f"    {child.name}/")
                        else:
                            lines.append(f"    {child.name}")
                except PermissionError:
                    pass

                # Indicate if there are more
                try:
                    total_children = len(list(entry.iterdir()))
                    if total_children > 8:
                        lines.append(
                            f"    ... and {total_children - 8} more"
                        )
                except PermissionError:
                    pass

            else:
                lines.append(f"  {entry.name}")

    except PermissionError:
        lines.append("  [Permission denied]")

    return "\n".join(lines)


def _select_important_files(
    context: RepositoryContext,
    repo_path: Path,
) -> list[dict]:
    """Select and read important files based on context."""

    files = []
    total_chars = 0

    # Sort by priority
    sorted_files = sorted(
        context.important_files,
        key=lambda f: _get_priority(Path(f.path)),
    )

    for file_ref in sorted_files:
        if total_chars >= MAX_TOTAL_CONTEXT_CHARS:
            break

        file_path = repo_path / file_ref.path

        if not file_path.exists():
            continue

        content = _read_file_safely(file_path)

        if content:
            files.append({
                "path": file_ref.path,
                "category": file_ref.category,
                "content": content,
            })
            total_chars += len(content)

    return files


def _select_source_files(
    repo_path: Path,
    already_selected: list[dict],
) -> list[dict]:
    """Select a few key source files for context."""

    already_paths = {f["path"] for f in already_selected}
    files = []
    total_chars = sum(len(f["content"]) for f in already_selected)

    # Find source files in source directories
    source_dirs = ["app", "src", "backend", "lib"]

    for dir_name in source_dirs:
        dir_path = repo_path / dir_name

        if not dir_path.exists() or not dir_path.is_dir():
            continue

        for file_path in sorted(dir_path.rglob("*")):
            if total_chars >= MAX_TOTAL_CONTEXT_CHARS:
                return files

            if not file_path.is_file():
                continue

            if file_path.suffix.lower() not in SOURCE_EXTENSIONS:
                continue

            relative = str(file_path.relative_to(repo_path))

            if relative in already_paths:
                continue

            # Skip very large files
            try:
                if file_path.stat().st_size > 50_000:
                    continue
            except OSError:
                continue

            content = _read_file_safely(file_path)

            if content and len(content) > 50:
                files.append({
                    "path": relative,
                    "category": "source",
                    "content": content,
                })
                total_chars += len(content)

                # Limit to 5 source files
                if len(files) >= 5:
                    return files

    return files
