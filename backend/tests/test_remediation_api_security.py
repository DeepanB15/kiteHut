"""
Security regression tests for the remediation API boundary.

The tests build a minimal FastAPI app around the agent router instead of
importing ``app.main``, so the module-level ``init_db()`` never runs and no
database is touched.
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.action.models.patch import ActionResult
from app.agent.permissions.policies import (
    DecisionType,
    PermissionRequest,
    PermissionType,
    RiskLevel,
)
from app.api import agent_routes
from app.core.config import settings

REMEDIATE_URL = "/api/v1/agent/remediate"
TOKEN = "test-remediation-token"


class FakeRemediationLoop:
    """Records how the endpoint constructs and calls the remediation loop."""

    created: list["FakeRemediationLoop"] = []

    def __init__(self, repository_path, permission_manager=None, llm_provider=None):
        self.repository_path = repository_path
        self.permission_manager = permission_manager
        self.calls: list[dict] = []
        FakeRemediationLoop.created.append(self)

    def remediate_finding(self, **kwargs):
        self.calls.append(kwargs)
        return ActionResult(
            success=True,
            finding_id=kwargs["finding"].finding_id,
            message="fake remediation",
        )


@pytest.fixture(autouse=True)
def reset_fake_loop(monkeypatch):
    FakeRemediationLoop.created = []
    monkeypatch.setattr(agent_routes, "ActionRemediationLoop", FakeRemediationLoop)


@pytest.fixture
def api_client():
    app = FastAPI()
    app.include_router(agent_routes.router)
    return TestClient(app)


@pytest.fixture
def repo(tmp_path):
    root = tmp_path / "repo"
    (root / "src").mkdir(parents=True)
    (root / "src" / "app.py").write_text("value = 1\n", encoding="utf-8")
    return root


@pytest.fixture
def approver_headers(monkeypatch, repo):
    """Configure a server-side approver and allowlist this test repository."""
    monkeypatch.setattr(settings, "REMEDIATION_API_TOKEN", TOKEN)
    monkeypatch.setattr(settings, "REMEDIATION_ALLOWED_REPOSITORIES", str(repo))
    return {"Authorization": f"Bearer {TOKEN}"}


def payload(repo, **extra):
    body = {
        "repository_path": str(repo),
        "finding_id": "fnd_api_security_1",
        "run_tests": False,
    }
    body.update(extra)
    return body


def test_client_auto_approve_is_rejected(api_client, approver_headers, repo):
    """The public contract must not let a request grant itself approval."""
    response = api_client.post(
        REMEDIATE_URL,
        json=payload(repo, auto_approve=True),
        headers=approver_headers,
    )

    assert response.status_code == 422
    assert FakeRemediationLoop.created == []


def test_missing_server_approver_fails_closed(api_client, monkeypatch, repo):
    """With no server-side approver configured, remediation is disabled."""
    monkeypatch.setattr(settings, "REMEDIATION_API_TOKEN", "")
    monkeypatch.setattr(settings, "REMEDIATION_ALLOWED_REPOSITORIES", str(repo))

    response = api_client.post(REMEDIATE_URL, json=payload(repo))

    assert response.status_code == 503
    assert FakeRemediationLoop.created == []


def test_missing_credentials_are_rejected(api_client, approver_headers, repo):
    """An unauthenticated client cannot start remediation."""
    response = api_client.post(REMEDIATE_URL, json=payload(repo))

    assert response.status_code == 401
    assert FakeRemediationLoop.created == []


def test_invalid_credentials_are_rejected(api_client, approver_headers, repo):
    """A wrong token cannot start remediation."""
    response = api_client.post(
        REMEDIATE_URL,
        json=payload(repo),
        headers={"Authorization": "Bearer wrong-token"},
    )

    assert response.status_code == 401
    assert FakeRemediationLoop.created == []


def test_repository_outside_allowlist_is_rejected(
    api_client, approver_headers, repo, tmp_path
):
    """A repository outside the server allowlist cannot be remediated."""
    unauthorized = tmp_path / "outside"
    unauthorized.mkdir()

    response = api_client.post(
        REMEDIATE_URL,
        json=payload(unauthorized),
        headers=approver_headers,
    )

    assert response.status_code == 403
    assert FakeRemediationLoop.created == []


def test_traversal_out_of_allowlist_is_rejected(
    api_client, approver_headers, repo, tmp_path
):
    """A '..' escape out of the allowlisted root is rejected."""
    unauthorized = tmp_path / "outside_traversal"
    unauthorized.mkdir()
    escape_path = str(repo / ".." / unauthorized.name)

    response = api_client.post(
        REMEDIATE_URL,
        json=payload(escape_path),
        headers=approver_headers,
    )

    assert response.status_code == 403
    assert FakeRemediationLoop.created == []


def test_empty_allowlist_denies_authorized_token(
    api_client, monkeypatch, approver_headers, repo
):
    """Even with a valid token, no allowlist means remediation is denied."""
    monkeypatch.setattr(settings, "REMEDIATION_ALLOWED_REPOSITORIES", "")

    response = api_client.post(
        REMEDIATE_URL,
        json=payload(repo),
        headers=approver_headers,
    )

    assert response.status_code == 403
    assert FakeRemediationLoop.created == []


def test_authorized_request_uses_server_side_approval(
    api_client, approver_headers, repo
):
    """An authenticated, allowlisted request is approved by the server itself."""
    response = api_client.post(
        REMEDIATE_URL,
        json=payload(repo),
        headers=approver_headers,
    )

    assert response.status_code == 200
    assert response.json()["success"] is True

    loop = FakeRemediationLoop.created[0]
    assert loop.repository_path == str(repo.resolve())
    assert "auto_approve" not in loop.calls[0]

    permission_manager = loop.permission_manager
    assert permission_manager is not None
    assert permission_manager.approval_callback is not None

    request = PermissionRequest(
        request_id="req_api_test",
        task_id="task_api_test",
        permission_type=PermissionType.WRITE,
        risk_level=RiskLevel.APPROVAL_REQUIRED,
        tool_name="apply_patch",
        description="Apply patch",
        repository_path=str(repo),
    )
    assert permission_manager.check_permission(request) is True
    assert (
        permission_manager.approval_callback(request) == DecisionType.ALLOW_ONCE
    )
