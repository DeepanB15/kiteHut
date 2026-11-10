from collections import Counter
from pathlib import Path

from app.models.scanner import (
    ScanResult,
    ImportantFile,
    DirectoryInfo,
)


# Files/directories we should ignore during scanning
IGNORE_DIRECTORIES = {
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
}


# Extension → Programming Language
LANGUAGE_MAP = {
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
}


# Important file names and their categories
IMPORTANT_FILES = {
    "readme.md": "documentation",

    "requirements.txt": "dependencies",
    "pyproject.toml": "dependencies",
    "poetry.lock": "dependencies",

    "package.json": "dependencies",
    "package-lock.json": "dependencies",

    "pom.xml": "dependencies",
    "build.gradle": "dependencies",

    "dockerfile": "containerization",
    "docker-compose.yml": "containerization",
    "docker-compose.yaml": "containerization",

    ".env.example": "configuration",
    ".gitignore": "configuration",

    "main.py": "possible_entry_point",
    "app.py": "possible_entry_point",
    "manage.py": "possible_entry_point",

    "main.java": "possible_entry_point",
}


DIRECTORY_RULES = {
    "src": "source",
    "app": "source",
    "backend": "source",
    "frontend": "frontend",

    "tests": "tests",
    "test": "tests",
    "__tests__": "tests",

    "docs": "documentation",
    "documentation": "documentation",

    "config": "configuration",
    "configs": "configuration",

    "scripts": "scripts",

    "models": "application_component",
    "services": "application_component",
    "controllers": "application_component",
    "routes": "application_component",
}
def should_ignore(path: Path) -> bool:
    """
    Check whether a path contains an ignored directory.
    """

    return any(part in IGNORE_DIRECTORIES for part in path.parts)

def scan_repository(repository_path: str) -> ScanResult:
    """
    Scan a repository and extract deterministic metadata.
    """

    repo_path = Path(repository_path)

    if not repo_path.exists():
        raise FileNotFoundError(
            f"Repository path does not exist: {repository_path}"
        )

    if not repo_path.is_dir():
        raise NotADirectoryError(
            f"Repository path is not a directory: {repository_path}"
        )

    extension_counter = Counter()
    language_counter = Counter()

    important_files = []
    directories = []

    total_files = 0
    total_directories = 0

    for path in repo_path.rglob("*"):

        relative_path = path.relative_to(repo_path)

        # Ignore unnecessary directories/files
        if should_ignore(relative_path):
            continue

        if path.is_file():

            total_files += 1

            extension = path.suffix.lower()

            if extension:
                extension_counter[extension] += 1

                language = LANGUAGE_MAP.get(extension)

                if language:
                    language_counter[language] += 1

            file_name = path.name.lower()

            if file_name in IMPORTANT_FILES:

                important_files.append(
                    ImportantFile(
                        path=str(relative_path),
                        category=IMPORTANT_FILES[file_name]
                    )
                )

        elif path.is_dir():

            total_directories += 1

            directory_name = path.name.lower()

            category = DIRECTORY_RULES.get(directory_name)

            if category:

                directories.append(
                    DirectoryInfo(
                        path=str(relative_path),
                        category=category
                    )
                )

    return ScanResult(
        total_files=total_files,
        total_directories=total_directories,
        extensions=dict(extension_counter),
        languages=dict(language_counter),
        important_files=important_files,
        directories=directories,
    )