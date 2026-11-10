from pathlib import Path

from app.models.analysis import RepositoryInfo
from app.models.scanner import ScanResult
from app.models.repository_context import (
    RepositoryContext,
    RepositoryStatistics,
    ProjectStructure,
    FileReference,
)

# Technology detection rules: name → (files to check, keywords inside those files)
TECHNOLOGY_RULES = {
    "FastAPI": {
        "files": ["requirements.txt", "pyproject.toml"],
        "keywords": ["fastapi"]
    },

    "Flask": {
        "files": ["requirements.txt", "pyproject.toml"],
        "keywords": ["flask"]
    },

    "Django": {
        "files": ["requirements.txt", "pyproject.toml"],
        "keywords": ["django"]
    },

    "React": {
        "files": ["package.json"],
        "keywords": ["react"]
    },

    "Next.js": {
        "files": ["package.json"],
        "keywords": ["next"]
    },

    "Express": {
        "files": ["package.json"],
        "keywords": ["express"]
    },

    "Spring Boot": {
        "files": ["pom.xml", "build.gradle"],
        "keywords": [
            "spring-boot",
            "org.springframework.boot"
        ]
    },

    "Docker": {
        "files": [
            "dockerfile",
            "docker-compose.yml",
            "docker-compose.yaml"
        ],
        "keywords": []
    },
}

# Directories to skip during technology detection
SKIP_DIRECTORIES = {
    ".git",
    "node_modules",
    ".venv",
    "venv",
    "__pycache__",
}

# Minimum ratio of matches relative to the top technology to keep it.
# e.g., 0.2 means a technology must have at least 20% as many matches
# as the most prevalent one to be included.
PREVALENCE_THRESHOLD = 0.2


def read_file_safely(file_path: Path) -> str:
    """
    Read a text file safely.

    Returns an empty string if the file cannot be read.
    """

    try:
        return file_path.read_text(
            encoding="utf-8",
            errors="ignore"
        ).lower()

    except Exception:
        return ""


def detect_technologies(repository_path: str) -> list[str]:
    """
    Detect technologies based on known dependency/config files.

    Returns technologies ranked by prevalence (most matches first),
    filtering out technologies that fall below the prevalence threshold
    relative to the most detected technology.
    """

    repo_path = Path(repository_path)

    # Count how many file matches each technology gets
    match_counts: dict[str, int] = {}

    for technology, rule in TECHNOLOGY_RULES.items():

        for file_name in rule["files"]:

            matching_files = list(
                repo_path.rglob(file_name)
            )

            for file_path in matching_files:

                # Ignore .git/node_modules etc.
                if any(
                    part in SKIP_DIRECTORIES
                    for part in file_path.parts
                ):
                    continue

                # Docker only requires the file to exist
                if not rule["keywords"]:
                    match_counts[technology] = (
                        match_counts.get(technology, 0) + 1
                    )
                    break

                content = read_file_safely(file_path)

                if any(
                    keyword in content
                    for keyword in rule["keywords"]
                ):
                    match_counts[technology] = (
                        match_counts.get(technology, 0) + 1
                    )
                    break

    if not match_counts:
        return []

    # Sort by match count descending
    ranked = sorted(
        match_counts.items(),
        key=lambda item: item[1],
        reverse=True,
    )

    max_count = ranked[0][1]

    # Filter out technologies below the prevalence threshold
    filtered = [
        tech for tech, count in ranked
        if count >= max_count * PREVALENCE_THRESHOLD
    ]

    return filtered


def build_project_structure(
    scan_result: ScanResult
) -> ProjectStructure:
    """
    Organize scanned directories into a structured format.
    """

    source_directories = []
    test_directories = []
    frontend_directories = []
    documentation_directories = []
    configuration_directories = []
    application_components = []

    for directory in scan_result.directories:

        if directory.category == "source":
            source_directories.append(directory.path)

        elif directory.category == "tests":
            test_directories.append(directory.path)

        elif directory.category == "frontend":
            frontend_directories.append(directory.path)

        elif directory.category == "documentation":
            documentation_directories.append(directory.path)

        elif directory.category == "configuration":
            configuration_directories.append(directory.path)

        elif directory.category == "application_component":
            application_components.append(directory.path)

    return ProjectStructure(
        source_directories=source_directories,
        test_directories=test_directories,
        frontend_directories=frontend_directories,
        documentation_directories=documentation_directories,
        configuration_directories=configuration_directories,
        application_components=application_components,
    )


def build_repository_context(
    repository: RepositoryInfo,
    scan_result: ScanResult,
) -> RepositoryContext:
    """
    Build a standardized repository context from
    repository information and scanner results.
    """

    repository_path = repository.local_path

    technologies = detect_technologies(
        repository_path
    )

    structure = build_project_structure(
        scan_result
    )

    important_files = [
        FileReference(
            path=file.path,
            category=file.category
        )
        for file in scan_result.important_files
    ]

    entry_points = [
        file.path
        for file in scan_result.important_files
        if file.category == "possible_entry_point"
    ]

    statistics = RepositoryStatistics(
        total_files=scan_result.total_files,
        total_directories=scan_result.total_directories,
        extensions=scan_result.extensions,
    )

    return RepositoryContext(
        repository_name=repository.name,
        repository_owner=repository.owner,
        repository_url=repository.url,

        statistics=statistics,

        languages=scan_result.languages,
        technologies=technologies,

        important_files=important_files,
        entry_points=entry_points,

        structure=structure,
    )
