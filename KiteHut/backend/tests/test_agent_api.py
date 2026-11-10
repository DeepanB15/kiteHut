"""
Unit and integration tests for Agent Core & Continuous Guardian API/WebSocket layer (Option A).
"""

import json
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from app.agent.runtime.core import get_agent_core
from app.agent.state.agent_state import TaskStatus
from app.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def disable_llm():
    """Ensure tests run deterministic heuristic planning and execution without waiting for external LLMs."""
    core = get_agent_core()
    old_llm = core.llm
    core.llm = None
    yield
    core.llm = old_llm


class TestAgentTaskEndpoints:
    """Test REST endpoints for task creation, inspection, execution, and rollback."""

    def test_create_task_success(self, temp_git_repo):
        repo_path = str(temp_git_repo)
        response = client.post(
            "/api/v1/agent/tasks",
            json={
                "repository_path": repo_path,
                "user_goal": "Inspect code structure and create documentation",
                "auto_allow_safe": True,
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["task_id"].startswith("task_")
        assert data["repository_path"] == str(Path(repo_path).resolve())
        assert data["user_goal"] == "Inspect code structure and create documentation"
        assert data["status"] == "PENDING"

    def test_create_task_invalid_repo(self):
        response = client.post(
            "/api/v1/agent/tasks",
            json={
                "repository_path": "/non/existent/path/xyz_123",
                "user_goal": "Fix something",
            },
        )
        assert response.status_code == 400

    def test_list_tasks(self, temp_git_repo):
        repo_path = str(temp_git_repo)
        client.post(
            "/api/v1/agent/tasks",
            json={
                "repository_path": repo_path,
                "user_goal": "List task test",
            },
        )
        response = client.get("/api/v1/agent/tasks")
        assert response.status_code == 200
        data = response.json()
        assert "tasks" in data
        assert data["total"] >= 1
        assert any(t["user_goal"] == "List task test" for t in data["tasks"])

    def test_get_task_details(self, temp_git_repo):
        repo_path = str(temp_git_repo)
        create_res = client.post(
            "/api/v1/agent/tasks",
            json={
                "repository_path": repo_path,
                "user_goal": "Get task test",
            },
        )
        task_id = create_res.json()["task_id"]

        get_res = client.get(f"/api/v1/agent/tasks/{task_id}")
        assert get_res.status_code == 200
        assert get_res.json()["task_id"] == task_id

        # 404 for invalid task
        not_found_res = client.get("/api/v1/agent/tasks/task_invalid_999")
        assert not_found_res.status_code == 404

    def test_run_task_synchronous(self, temp_git_repo):
        repo_path = str(temp_git_repo)
        create_res = client.post(
            "/api/v1/agent/tasks",
            json={
                "repository_path": repo_path,
                "user_goal": "Analyze repository architecture",
                "auto_allow_safe": True,
            },
        )
        task_id = create_res.json()["task_id"]

        run_res = client.post(f"/api/v1/agent/tasks/{task_id}/run")
        assert run_res.status_code == 200
        data = run_res.json()
        assert data["task_id"] == task_id
        assert data["status"] in ("COMPLETED", "WAITING_APPROVAL", "RUNNING")
        assert data["plan"] is not None

    def test_cancel_task(self, temp_git_repo):
        repo_path = str(temp_git_repo)
        create_res = client.post(
            "/api/v1/agent/tasks",
            json={
                "repository_path": repo_path,
                "user_goal": "Task to cancel",
            },
        )
        task_id = create_res.json()["task_id"]

        cancel_res = client.post(f"/api/v1/agent/tasks/{task_id}/cancel")
        assert cancel_res.status_code == 200
        assert cancel_res.json()["status"] == "CANCELLED"

    def test_rollback_task(self, temp_git_repo):
        repo_path = str(temp_git_repo)
        core = get_agent_core()
        state = core.create_task(
            repository_path=repo_path,
            user_goal="Modify file then rollback",
            auto_allow_all=True,
        )
        task_id = state.task_id

        # Simulate snapshotting and modifying a file
        memory = core.memories[task_id]
        memory.record_file_snapshot("src/main.py")
        (Path(repo_path) / "src" / "main.py").write_text("def modified(): pass\n", encoding="utf-8")

        # Rollback via API
        rollback_res = client.post(f"/api/v1/agent/tasks/{task_id}/rollback")
        assert rollback_res.status_code == 200
        data = rollback_res.json()
        assert data["success"] is True
        assert "src/main.py" in data["restored_files"]

        # Verify content was restored
        restored_content = (Path(repo_path) / "src" / "main.py").read_text(encoding="utf-8")
        assert "def add" in restored_content


class TestRemediationEndpoint:
    """Test autonomous remediation endpoint."""

    def test_remediate_finding_endpoint(self, temp_git_repo):
        repo_path = str(temp_git_repo)
        finding_data = {
            "finding_id": "fnd_api_test_01",
            "category": "security",
            "severity": "high",
            "title": "Missing security configuration file",
            "description": "Ensure configuration security parameters are present.",
            "file_path": "src/main.py",
        }

        res = client.post(
            "/api/v1/agent/remediate",
            json={
                "repository_path": repo_path,
                "finding_data": finding_data,
                "auto_approve": True,
                "run_tests": False,
            },
        )
        assert res.status_code == 200
        data = res.json()
        assert data["finding_id"] == "fnd_api_test_01"
        assert "action_id" in data


class TestAgentWebSocket:
    """Test real-time interactive WebSocket stream for agent tasks."""

    def test_agent_websocket_flow(self, temp_git_repo):
        repo_path = str(temp_git_repo)
        create_res = client.post(
            "/api/v1/agent/tasks",
            json={
                "repository_path": repo_path,
                "user_goal": "WebSocket integration test",
                "auto_allow_safe": True,
            },
        )
        task_id = create_res.json()["task_id"]

        with client.websocket_connect(f"/api/v1/agent/ws/{task_id}") as ws:
            # 1. Connected event received
            initial = ws.receive_json()
            assert initial["event"] == "connected"
            assert initial["task_id"] == task_id

            # 2. Ping / Pong
            ws.send_json({"action": "ping"})
            pong = ws.receive_json()
            assert pong["event"] == "pong"

            # 3. Get State
            ws.send_json({"action": "get_state"})
            state_msg = ws.receive_json()
            assert state_msg["event"] == "task_state"
            assert state_msg["task_id"] == task_id

            # 4. Trigger Run via WebSocket
            ws.send_json({"action": "run"})
            # Should receive execution events
            event = ws.receive_json()
            assert "event" in event


class TestMonitoringEndpoints:
    """Test Continuous Guardian monitoring endpoints and WebSocket."""

    def test_monitoring_check_endpoint(self, temp_git_repo):
        repo_path = str(temp_git_repo)
        res = client.post(
            "/api/v1/monitoring/check",
            json={"repository_path": repo_path},
        )
        assert res.status_code == 200
        data = res.json()
        assert "report_id" in data
        assert "changed_events" in data
        assert "impacted_files" in data
        assert "duration_ms" in data

    def test_monitoring_status_endpoint(self, temp_git_repo):
        repo_path = str(temp_git_repo)
        res = client.get(f"/api/v1/monitoring/status?repository_path={repo_path}")
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "active"
        assert data["repository_path"] == str(Path(repo_path).resolve())

    def test_monitoring_websocket(self, temp_git_repo):
        repo_path = str(temp_git_repo)
        with client.websocket_connect("/api/v1/monitoring/ws") as ws:
            # 1. Connected event
            connected = ws.receive_json()
            assert connected["event"] == "connected"

            # 2. Ping / Pong
            ws.send_json({"action": "ping"})
            pong = ws.receive_json()
            assert pong["event"] == "pong"

            # 3. Check now
            ws.send_json({"action": "check_now", "repository_path": repo_path})
            check_res = ws.receive_json()
            assert check_res["event"] == "check_result"
            assert "report_id" in check_res["report"]
