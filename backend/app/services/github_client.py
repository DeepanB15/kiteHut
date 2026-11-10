"""
GitHub API Client (Phase 9).

Thin httpx client for the GitHub REST API. Uses a Personal Access
Token from settings when configured (required for private repos and
for posting PR comments); public repositories work without a token.

Endpoints used:
    GET  /user
    GET  /rate_limit
    GET  /repos/{owner}/{repo}
    GET  /repos/{owner}/{repo}/pulls/{number}
    GET  /repos/{owner}/{repo}/pulls/{number}/files
    POST /repos/{owner}/{repo}/issues/{number}/comments
"""

import logging
from typing import Any

import httpx

from app.core.config import settings

logger = logging.getLogger("repolens.github")


class GitHubError(Exception):
    """Base error for GitHub API failures."""


class GitHubNotFound(GitHubError):
    """Resource does not exist (or is private without a token)."""


class GitHubAuthError(GitHubError):
    """Authentication / authorization problem."""


class GitHubClient:
    """Client for the GitHub REST API."""

    def __init__(
        self,
        token: str | None = None,
        base_url: str | None = None,
        timeout: float = 20.0,
    ):
        self.token = token or settings.github_token
        self.base_url = (base_url or settings.GITHUB_API_URL).rstrip("/")
        self.timeout = timeout

        headers = {
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        self._client = httpx.Client(
            base_url=self.base_url,
            headers=headers,
            timeout=timeout,
        )
        self._auth_user: dict | None = None

    # ============================================================
    # Low-level helpers
    # ============================================================

    def _request(self, method: str, path: str, **kwargs) -> Any:
        try:
            response = self._client.request(method, path, **kwargs)
        except httpx.HTTPError as error:
            raise GitHubError(f"GitHub API unreachable: {error}") from error

        if response.status_code == 404:
            raise GitHubNotFound(
                f"GitHub resource not found: {path} "
                "(private repositories require a GITHUB_TOKEN)"
            )
        if response.status_code in (401, 403):
            raise GitHubAuthError(
                f"GitHub API authorization failed ({response.status_code}) "
                "on {path}. Check GITHUB_TOKEN."
            )
        if response.status_code >= 400:
            raise GitHubError(
                f"GitHub API error {response.status_code} on {path}: "
                f"{response.text[:300]}"
            )

        if response.status_code == 204:
            return None
        return response.json()

    def _get(self, path: str, params: dict | None = None) -> Any:
        return self._request("GET", path, params=params)

    def _post(self, path: str, payload: dict) -> Any:
        return self._request("POST", path, json=payload)

    def close(self) -> None:
        self._client.close()

    # ============================================================
    # Authentication / account
    # ============================================================

    def is_authenticated(self) -> bool:
        """True when a token is configured and valid."""
        if not self.token:
            return False
        try:
            self.get_authenticated_user()
            return True
        except GitHubError:
            return False

    def get_authenticated_user(self) -> dict | None:
        """Return the authenticated user (cached) or None when anonymous."""
        if not self.token:
            return None
        if self._auth_user is None:
            self._auth_user = self._get("/user")
        return self._auth_user

    def get_rate_limit(self) -> dict | None:
        """Return core rate limit info, or None when unavailable."""
        try:
            data = self._get("/rate_limit")
            return data.get("resources", {}).get("core", {})
        except GitHubError:
            return None

    # ============================================================
    # Repositories
    # ============================================================

    def get_repository(self, owner: str, repo: str) -> dict:
        return self._get(f"/repos/{owner}/{repo}")

    # ============================================================
    # Pull requests
    # ============================================================

    def get_pull_request(self, owner: str, repo: str, number: int) -> dict:
        return self._get(f"/repos/{owner}/{repo}/pulls/{number}")

    def get_pull_request_files(
        self,
        owner: str,
        repo: str,
        number: int,
        max_files: int | None = None,
    ) -> list[dict]:
        """
        Fetch the files changed by a pull request, with patches.

        Results are paginated and capped at max_files (or
        settings.PR_MAX_CHANGED_FILES).
        """
        limit = max_files or settings.PR_MAX_CHANGED_FILES
        files: list[dict] = []
        page = 1

        while len(files) < limit:
            batch = self._get(
                f"/repos/{owner}/{repo}/pulls/{number}/files",
                params={"per_page": 100, "page": page},
            )
            if not batch:
                break
            files.extend(batch)
            if len(batch) < 100:
                break
            page += 1

        return files[:limit]

    def post_pull_request_comment(
        self,
        owner: str,
        repo: str,
        number: int,
        body: str,
    ) -> dict:
        """Post an issue-style comment on the pull request."""
        if not self.token:
            raise GitHubAuthError(
                "Cannot post PR comments without a GITHUB_TOKEN"
            )
        return self._post(
            f"/repos/{owner}/{repo}/issues/{number}/comments",
            {"body": body},
        )

    # ============================================================
    # Commit status checks
    # ============================================================

    def create_commit_status(
        self,
        owner: str,
        repo: str,
        sha: str,
        state: str,
        context: str = "RepoLens/Quality-Gate",
        description: str = "",
        target_url: str | None = None,
    ) -> dict:
        """
        Create or update a commit status for a SHA.

        `state` is one of: error, failure, pending, success.
        Requires a GITHUB_TOKEN (classic PAT with repo scope, or a
        fine-grained token with "Commit statuses" write permission).
        """
        if not self.token:
            raise GitHubAuthError(
                "Cannot create commit statuses without a GITHUB_TOKEN"
            )
        if state not in ("error", "failure", "pending", "success"):
            raise GitHubError(f"Invalid commit status state: {state}")

        payload: dict = {"state": state, "context": context}
        if description:
            payload["description"] = description[:140]
        if target_url:
            payload["target_url"] = target_url
        return self._post(
            f"/repos/{owner}/{repo}/statuses/{sha}",
            payload,
        )