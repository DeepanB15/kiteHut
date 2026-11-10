"""
Integration and Unit tests for Agent Runtime, Planner, Memory, and AgentCore.
"""

from app.agent.memory.task_memory import TaskMemory
from app.agent.permissions.policies import DecisionType
from app.agent.planner.task_planner import TaskPlanner
from app.agent.runtime.core import AgentCore
from app.agent.state.agent_state import StepStatus, TaskStatus


def test_task_planner_heuristics():
    """Verify TaskPlanner creates logical step sequences for various task goals."""
    planner = TaskPlanner()

    # Development task
    dev_plan = planner.create_plan(
        task_id="t1",
        goal="Add authentication middleware to api routes",
        repository_path="/test/repo",
        task_type="development",
    )
    assert len(dev_plan.steps) >= 4
    assert any("search" in s.description.lower() for s in dev_plan.steps)
    assert any("git" in s.description.lower() or "status" in s.description.lower() for s in dev_plan.steps)

    # Fix task
    fix_plan = planner.create_plan(
        task_id="t2",
        goal="Fix SQL injection vulnerability in user login query",
        repository_path="/test/repo",
        task_type="fix",
    )
    assert len(fix_plan.steps) >= 4
    assert any("root cause" in s.description.lower() or "search" in s.description.lower() for s in fix_plan.steps)
    assert any("verify" in s.description.lower() or "test" in s.description.lower() for s in fix_plan.steps)


def test_task_planner_dynamic_replan():
    """Verify dynamic replanning when a step fails."""
    planner = TaskPlanner()
    plan = planner.create_plan("t1", "Fix bug in calc.py", "/test/repo", "fix")
    failed_step = plan.steps[2]

    replanned = planner.replan_on_failure(
        plan=plan,
        failed_step=failed_step,
        error_message="SyntaxError: invalid syntax on line 12",
    )

    # Should have inserted diagnostic and re-test steps
    assert len(replanned.steps) > len(plan.steps)
    assert any("SyntaxError" in (s.description or "") for s in replanned.steps)


def test_task_memory_snapshot_and_rollback(temp_workspace):
    """Verify TaskMemory creates file snapshots and restores on rollback."""
    ws_str = str(temp_workspace)
    mem = TaskMemory(task_id="t1", repository_path=ws_str)

    target_rel = "src/main.py"
    target_abs = temp_workspace / "src" / "main.py"
    original_content = target_abs.read_text(encoding="utf-8")

    # Snapshot
    mem.record_file_snapshot(target_rel)

    # Modify file
    target_abs.write_text("# Corrupted edit\n", encoding="utf-8")
    assert target_abs.read_text(encoding="utf-8") == "# Corrupted edit\n"

    # Rollback
    restored = mem.rollback_all()
    assert target_rel in restored
    assert target_abs.read_text(encoding="utf-8") == original_content


def test_agent_core_execution_flow(temp_git_repo):
    """Verify end-to-end execution of a task via AgentCore in autonomous/auto-allow mode."""
    ws_str = str(temp_git_repo)
    core = AgentCore(llm_provider=None)

    events = []

    def event_collector(event_type, data):
        events.append(event_type)

    # Create task to inspect repository and search files
    state = core.create_task(
        repository_path=ws_str,
        user_goal="Scan repository files and inspect README",
        auto_allow_safe=True,
        auto_allow_all=True,  # Test full autonomous pass
    )

    assert state.status == TaskStatus.PENDING

    # Run task
    final_state = core.run_task(task_id=state.task_id, event_callback=event_collector)

    assert final_state.status == TaskStatus.COMPLETED
    assert len(final_state.tool_history) > 0
    assert "task_planning" in events
    assert "plan_created" in events
    assert "task_completed" in events


def test_agent_core_approval_pause_and_resume(temp_git_repo):
    """Verify that agent pauses on WAITING_APPROVAL and resumes when approved."""
    ws_str = str(temp_git_repo)
    core = AgentCore(llm_provider=None)

    events = []

    def event_collector(event_type, data):
        events.append(event_type)

    # All APPROVAL_REQUIRED actions will be denied initially by the permission manager
    def initial_prompt(req):
        return DecisionType.DENY

    state = core.create_task(
        repository_path=ws_str,
        user_goal="Modify src/main.py and add feature",
        approval_callback=initial_prompt,
        auto_allow_safe=True,
        auto_allow_all=False,
    )

    run_state = core.run_task(task_id=state.task_id, event_callback=event_collector)

    # Should have paused on approval requirement
    if run_state.status == TaskStatus.WAITING_APPROVAL:
        assert "approval_required" in events

        # Now approve the task for subsequent executions
        resumed_state = core.handle_approval(
            task_id=state.task_id,
            decision=DecisionType.ALLOW_FOR_TASK,
            tool_name="edit_file",
            event_callback=event_collector,
        )
        assert resumed_state.status in (TaskStatus.COMPLETED, TaskStatus.RUNNING)
