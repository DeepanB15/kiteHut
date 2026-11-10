import re
from pathlib import Path
from urllib.parse import urlparse

from git import Repo, GitCommandError

from app.core.config import settings
from app.models.analysis import RepositoryInfo


BASE_DIR = Path(__file__).resolve().parent.parent.parent

WORKSPACE_DIR = BASE_DIR / "workspace"

# Owner/repo names on GitHub: letters, digits, dashes, dots, underscores
_REPOSITORY_PART = re.compile(r"^[A-Za-z0-9_.-]+$")

MAX_REPOSITORY_URL_LENGTH = 2048


class InvalidRepositoryURL(Exception):
    """Raised when the repository URL is invalid."""


class RepositoryCloneError(Exception):
    """Raised when cloning a repository fails."""


def validate_github_repository_url(repository_url: str) -> tuple[str, str]:
    """
    Validate a repository URL for safe cloning.

    Rules (Phase 8 hardening):
    - Must be http(s)
    - Must not contain embedded credentials (user:pass@host)
    - Host must be in the allowed repository hosts (default: github.com)
    - Path must be <owner>/<repository> with valid name characters

    Expected format:
    https://github.com/<owner>/<repository>
    """

    if not repository_url or len(repository_url) > MAX_REPOSITORY_URL_LENGTH:
        raise InvalidRepositoryURL(
            f"Repository URL must be at most {MAX_REPOSITORY_URL_LENGTH} characters."
        )

    parsed = urlparse(repository_url)

    if parsed.scheme not in ("http", "https"):
        raise InvalidRepositoryURL(
            "Repository URL must use http or https."
        )

    # Never allow embedded credentials (blocks user:pass@host URLs)
    if parsed.username or parsed.password:
        raise InvalidRepositoryURL(
            "Repository URLs must not contain embedded credentials."
        )

    host = parsed.netloc.lower()
    if host.startswith("www."):
        host = host[4:]

    if host not in settings.allowed_repository_hosts:
        allowed = ", ".join(settings.allowed_repository_hosts)
        raise InvalidRepositoryURL(
            f"Repository host '{host}' is not allowed. Allowed hosts: {allowed}"
        )

    path_parts = [
        part for part in parsed.path.strip("/").split("/")
        if part
    ]

    if len(path_parts) != 2:
        raise InvalidRepositoryURL(
            "Repository URL must be in the format: "
            "https://github.com/<owner>/<repository>"
        )

    owner, repository = path_parts

    # Support URLs ending in .git
    if repository.endswith(".git"):
        repository = repository[:-4]

    if not owner or not repository:
        raise InvalidRepositoryURL(
            "GitHub owner and repository name are required."
        )

    if not _REPOSITORY_PART.match(owner) or not _REPOSITORY_PART.match(repository):
        raise InvalidRepositoryURL(
            "Repository owner and name may only contain letters, digits, "
            "dashes, dots, and underscores."
        )

    return owner, repository


def clone_repository(
    repository_url: str,
    analysis_id: str
) -> RepositoryInfo:
    """
    Clone a public GitHub repository into an isolated workspace.
    """

    owner, repository_name = validate_github_repository_url(
        repository_url
    )

    analysis_workspace = (
        WORKSPACE_DIR / analysis_id
    )

    repository_path = (
        analysis_workspace / "repository"
    )

    # Create workspace directory
    analysis_workspace.mkdir(
        parents=True,
        exist_ok=True
    )

    try:
        Repo.clone_from(
            repository_url,
            repository_path
        )

    except GitCommandError as error:

        # Cleanup failed clone
        if repository_path.exists():
            import shutil
            shutil.rmtree(
                repository_path,
                ignore_errors=True
            )

        raise RepositoryCloneError(
            f"Failed to clone repository: {error}"
        )

    return RepositoryInfo(
        name=repository_name,
        owner=owner,
        url=repository_url,
        local_path=str(repository_path.resolve())
    )