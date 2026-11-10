"""
Agent Core API and WebSocket Routes for RepoLens.

Endpoints for task lifecycles, interactive approvals, step-by-step WebSocket streaming,
workspace rollbacks, and autonomous remediations.
"""

import asyncio
from datetime import datetime, timezone
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import (
    APIRouter,
    BackgroundTasks,
    HTTPException,
    Query,
    WebSocket,
    WebSocketDisconnect,
    status,
)

from app.action.loop.remediation_loop import ActionRemediationLoop
from app.agent.permissions.policies import DecisionType
from app.agent.runtime.core import get_agent_core
from app.agent.state.agent_state import AgentState, TaskStatus
from app.intelligence.models.findings import Finding, FindingCategory, FindingSeverity
from app.models.agent_api import (
    AgentObservationResponse,
    AgentTaskListResponse,
    AgentTaskResponse,
    CreateAgentTaskRequest,
    PlanResponse,
    PlanStepResponse,
    RemediationRequest,
    RemediationResponse,
    TaskApprovalRequest,
    TaskRollbackResponse,
    ToolResultResponse,
)

logger = logging.getLogger("repolens.api.agent")

router = APIRouter(prefix="/api/v1/agent", tags=["Agent Core & Autonomy"])


def _state_to_response(state: AgentState) -> AgentTaskResponse:
    """Convert internal AgentState into typed API response model."""
    plan_resp = None
    if state.plan:
        steps_resp = [
            PlanStepResponse(
                step_id=s.step_id,
                description=s.description,
                tool_name=s.tool_name,
                arguments=s.arguments,
                expected_output=s.expected_output,
                status=s.status,
                result=ToolResultResponse(
                    call_id=s.result.call_id,
                    tool_name=s.result.tool_name,
                    success=s.result.success,
                    output=s.result.output,
                    error=s.result.error,
                    duration_ms=s.result.duration_ms,
                    created_at=s.result.created_at,
                )
                if s.result
                else None,
                error=s.error,
            )
            for s in state.plan.steps
        ]
        plan_resp = PlanResponse(
            task_id=state.plan.task_id,
            goal=state.plan.goal,
            steps=steps_resp,
            created_at=state.plan.created_at,
            status=state.plan.status,
        )

    tool_history = [
        ToolResultResponse(
            call_id=tr.call_id,
            tool_name=tr.tool_name,
            success=tr.success,
            output=tr.output,
            error=tr.error,
            duration_ms=tr.duration_ms,
            created_at=tr.created_at,
        )
        for tr in state.tool_history
    ]

    observations = [
        AgentObservationResponse(
            step_id=obs.step_id,
            observation=obs.observation,
            timestamp=obs.timestamp,
        )
        for obs in state.observations
    ]

    return AgentTaskResponse(
        task_id=state.task_id,
        session_id=state.session_id,
        repository_path=state.repository_path,
        user_goal=state.user_goal,
        status=state.status,
        plan=plan_resp,
        current_step_index=state.current_step_index,
        tool_history=tool_history,
        observations=observations,
        context_files=state.context_files,
        error_message=state.error_message,
        created_at=state.created_at,
        updated_at=state.updated_at,
    )


@router.post(
    "/tasks",
    response_model=AgentTaskResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new agent task",
)
def create_agent_task(request: CreateAgentTaskRequest):
    """
    Initialize an agent task in the workspace.
    Validates repository path and registers memory/permission managers.
    """
    repo_path = Path(request.repository_path).resolve()
    if not repo_path.exists() or not repo_path.is_dir():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Repository path '{request.repository_path}' does not exist or is not a directory.",
        )

    core = get_agent_core()
    state = core.create_task(
        repository_path=str(repo_path),
        user_goal=request.user_goal,
        session_id=request.session_id,
        auto_allow_safe=request.auto_allow_safe,
        auto_allow_all=request.auto_allow_all,
    )
    return _state_to_response(state)


@router.get(
    "/tasks",
    response_model=AgentTaskListResponse,
    summary="List all agent tasks",
)
def list_agent_tasks():
    """List all registered agent tasks."""
    core = get_agent_core()
    tasks = [_state_to_response(s) for s in core.tasks.values()]
    return AgentTaskListResponse(tasks=tasks, total=len(tasks))


@router.get(
    "/tasks/{task_id}",
    response_model=AgentTaskResponse,
    summary="Get task status and details",
)
def get_agent_task(task_id: str):
    """Retrieve detailed state and history for a specific task."""
    core = get_agent_core()
    state = core.get_task(task_id)
    if not state:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Task '{task_id}' not found.",
        )
    return _state_to_response(state)


@router.post(
    "/tasks/{task_id}/run",
    response_model=AgentTaskResponse,
    summary="Execute an agent task",
)
def run_agent_task(
    task_id: str,
    background: bool = Query(False, description="Run task in background"),
    background_tasks: BackgroundTasks = None,
):
    """
    Execute task execution loop until completion or an approval boundary.
    Can be run synchronously or asynchronously in the background.
    """
    core = get_agent_core()
    state = core.get_task(task_id)
    if not state:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Task '{task_id}' not found.",
        )

    if background:
        if background_tasks is not None:
            background_tasks.add_task(core.run_task, task_id)
        return _state_to_response(state)

    try:
        updated_state = core.run_task(task_id)
        return _state_to_response(updated_state)
    except Exception as error:
        logger.error("Error executing task %s: %s", task_id, error)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Task execution failed: {error}",
        )


@router.post(
    "/tasks/{task_id}/approval",
    response_model=AgentTaskResponse,
    summary="Submit user approval decision",
)
def handle_task_approval(task_id: str, request: TaskApprovalRequest):
    """
    Submit permission decision (ALLOW_ONCE, ALLOW_FOR_TASK, ALLOW_FOR_REPO, DENY)
    and resume task execution loop.
    """
    core = get_agent_core()
    state = core.get_task(task_id)
    if not state:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Task '{task_id}' not found.",
        )

    try:
        decision_enum = DecisionType(request.decision.upper())
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid decision '{request.decision}'. Must be one of: {[d.value for d in DecisionType]}",
        )

    try:
        updated_state = core.handle_approval(
            task_id=task_id,
            decision=decision_enum,
            tool_name=request.tool_name,
        )
        return _state_to_response(updated_state)
    except Exception as error:
        logger.error("Error submitting approval for task %s: %s", task_id, error)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to process approval: {error}",
        )


@router.post(
    "/tasks/{task_id}/cancel",
    response_model=AgentTaskResponse,
    summary="Cancel active agent task",
)
def cancel_agent_task(task_id: str):
    """Cancel an active or waiting agent task."""
    core = get_agent_core()
    success = core.cancel_task(task_id)
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Task '{task_id}' not found.",
        )
    state = core.get_task(task_id)
    return _state_to_response(state)


@router.post(
    "/tasks/{task_id}/rollback",
    response_model=TaskRollbackResponse,
    summary="Rollback workspace modifications",
)
def rollback_agent_task(task_id: str):
    """Restore all files modified during this task to their initial state."""
    core = get_agent_core()
    state = core.get_task(task_id)
    if not state:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Task '{task_id}' not found.",
        )

    try:
        restored = core.rollback_task(task_id)
        return TaskRollbackResponse(
            task_id=task_id,
            restored_files=restored,
            success=True,
            message=f"Successfully restored {len(restored)} file(s).",
        )
    except Exception as error:
        logger.error("Rollback failed for task %s: %s", task_id, error)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Rollback failed: {error}",
        )


@router.post(
    "/remediate",
    response_model=RemediationResponse,
    summary="Run autonomous remediation loop for a finding",
)
def remediate_finding_endpoint(request: RemediationRequest):
    """
    Execute autonomous Plan -> Permission -> Snapshot -> Apply -> Test -> Verify -> Rollback cycle.
    """
    repo_path = Path(request.repository_path).resolve()
    if not repo_path.exists() or not repo_path.is_dir():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Repository path '{request.repository_path}' does not exist.",
        )

    # 1. Resolve finding object
    target_finding: Optional[Finding] = None
    if request.finding_data:
        try:
            target_finding = Finding(**request.finding_data)
        except Exception as err:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Invalid finding data: {err}",
            )
    elif request.finding_id:
        target_finding = Finding(
            finding_id=request.finding_id,
            category=FindingCategory.QUALITY,
            severity=FindingSeverity.MEDIUM,
            title=f"Remediate finding {request.finding_id}",
            description="Autonomous remediation requested via API.",
        )
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Must provide either finding_id or finding_data.",
        )

    # 2. Execute remediation loop
    try:
        loop = ActionRemediationLoop(repository_path=str(repo_path))
        result = loop.remediate_finding(
            finding=target_finding,
            auto_approve=request.auto_approve,
            run_tests=request.run_tests,
            test_paths=request.test_paths,
        )

        test_dict = None
        if result.test_results:
            test_dict = {
                "passed": result.test_results.passed,
                "total_tests": result.test_results.total_tests,
                "passed_tests": result.test_results.passed_tests,
                "failed_tests": result.test_results.failed_tests,
                "output": result.test_results.output,
                "error_message": result.test_results.error_message,
                "duration_ms": result.test_results.duration_ms,
            }

        return RemediationResponse(
            action_id=result.action_id,
            finding_id=result.finding_id,
            success=result.success,
            applied_patch_id=result.applied_patch_id,
            modified_files=result.modified_files,
            test_results=test_dict,
            message=result.message,
            error=result.error,
            rolled_back=result.rolled_back,
        )
    except Exception as error:
        logger.error("Remediation loop error: %s", error)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Remediation failed: {error}",
        )


@router.websocket("/ws/{task_id}")
async def agent_task_websocket(websocket: WebSocket, task_id: str):
    """
    Real-time interactive WebSocket stream for an agent task.
    Streams plan generation, tool execution logs, observations, and interactive approvals.
    """
    await websocket.accept()
    core = get_agent_core()
    state = core.get_task(task_id)

    if not state:
        await websocket.send_json({
            "event": "error",
            "task_id": task_id,
            "message": f"Task '{task_id}' not found.",
        })
        await websocket.close(code=1008)
        return

    # Send initial connection state
    await websocket.send_json({
        "event": "connected",
        "task_id": task_id,
        "state": _state_to_response(state).model_dump(mode="json"),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })

    event_queue: asyncio.Queue = asyncio.Queue()
    async_loop = asyncio.get_running_loop()

    def threadsafe_event_callback(event_name: str, event_data: Dict[str, Any]):
        """Forward sync loop events into async queue."""
        # Sanitize event data to be JSON-serializable
        try:
            sanitized_data = json.loads(json.dumps(event_data, default=str))
        except Exception:
            sanitized_data = str(event_data)

        msg = {
            "event": event_name,
            "data": sanitized_data,
            "task_id": task_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        async_loop.call_soon_threadsafe(event_queue.put_nowait, msg)

    async def event_forwarder():
        """Continuously drain events from queue and send over WebSocket."""
        try:
            while True:
                msg = await event_queue.get()
                await websocket.send_json(msg)
                event_queue.task_done()
        except asyncio.CancelledError:
            pass
        except Exception as err:
            logger.debug("Event forwarder stopped: %s", err)

    forwarder_task = asyncio.create_task(event_forwarder())

    try:
        while True:
            raw_text = await websocket.receive_text()
            try:
                data = json.loads(raw_text)
            except json.JSONDecodeError:
                await websocket.send_json({"event": "error", "message": "Invalid JSON payload."})
                continue

            action = data.get("action", "").lower()

            if action == "ping":
                await websocket.send_json({"event": "pong", "timestamp": datetime.now(timezone.utc).isoformat()})

            elif action == "get_state":
                curr_state = core.get_task(task_id)
                if curr_state:
                    await websocket.send_json({
                        "event": "task_state",
                        "task_id": task_id,
                        "state": _state_to_response(curr_state).model_dump(mode="json"),
                    })

            elif action == "run":
                # Execute in background thread with live event stream
                await async_loop.run_in_executor(
                    None,
                    core.run_task,
                    task_id,
                    threadsafe_event_callback,
                )
                curr_state = core.get_task(task_id)
                await websocket.send_json({
                    "event": "execution_cycle_ended",
                    "task_id": task_id,
                    "status": curr_state.status.value if curr_state else "UNKNOWN",
                })

            elif action == "approval":
                decision_str = data.get("decision", "ALLOW_ONCE")
                tool_name = data.get("tool_name")
                try:
                    decision_enum = DecisionType(decision_str.upper())
                except ValueError:
                    await websocket.send_json({"event": "error", "message": f"Invalid decision '{decision_str}'."})
                    continue

                await async_loop.run_in_executor(
                    None,
                    core.handle_approval,
                    task_id,
                    decision_enum,
                    tool_name,
                    threadsafe_event_callback,
                )
                curr_state = core.get_task(task_id)
                await websocket.send_json({
                    "event": "execution_cycle_ended",
                    "task_id": task_id,
                    "status": curr_state.status.value if curr_state else "UNKNOWN",
                })

            elif action == "cancel":
                core.cancel_task(task_id)
                await websocket.send_json({
                    "event": "task_cancelled",
                    "task_id": task_id,
                })

            elif action == "rollback":
                restored = core.rollback_task(task_id)
                await websocket.send_json({
                    "event": "task_rolled_back",
                    "task_id": task_id,
                    "restored_files": restored,
                })

            else:
                await websocket.send_json({
                    "event": "warning",
                    "message": f"Unknown action: '{action}'. Available: run, approval, cancel, rollback, get_state, ping.",
                })

    except WebSocketDisconnect:
        logger.info("WebSocket disconnected for task: %s", task_id)
    finally:
        forwarder_task.cancel()
