"""
Task Planner for RepoLens Agent.

Decomposes user objectives into structured execution plans (PlanStep sequences),
supports dynamic replanning on tool failures, and provides heuristic fallback templates.
"""

from datetime import datetime, timezone
import json
import logging
from typing import Any, Dict, List, Optional

from app.agent.state.agent_state import Plan, PlanStep, StepStatus, TaskStatus
from app.llm.base import BaseLLMProvider

logger = logging.getLogger("repolens.agent.planner")


class TaskPlanner:
    """
    Creates and adapts execution plans for RepoLens tasks.
    """

    def __init__(self, llm_provider: Optional[BaseLLMProvider] = None):
        self.llm = llm_provider

    def create_plan(
        self,
        task_id: str,
        goal: str,
        repository_path: str,
        task_type: str = "development",
        project_context: Optional[Dict[str, Any]] = None,
    ) -> Plan:
        """
        Generate a multi-step execution plan for the given goal.
        Tries LLM-based planning first if provider is available, then falls back to heuristics.
        """
        if self.llm and self.llm.is_available():
            try:
                plan = self._generate_llm_plan(task_id, goal, repository_path, project_context)
                if plan and len(plan.steps) > 0:
                    return plan
            except Exception as error:
                logger.warning("LLM planning failed, falling back to heuristic planner: %s", error)

        return self._generate_heuristic_plan(task_id, goal, task_type)

    def replan_on_failure(
        self,
        plan: Plan,
        failed_step: PlanStep,
        error_message: str,
    ) -> Plan:
        """
        Dynamically adjusts the plan when a step fails.
        Inserts diagnostic and remediation steps before re-attempting or completing.
        """
        new_steps: List[PlanStep] = []
        next_step_id = 1

        for step in plan.steps:
            if step.step_id < failed_step.step_id:
                new_steps.append(step)
                next_step_id += 1
            elif step.step_id == failed_step.step_id:
                step.status = StepStatus.FAILED
                step.error = error_message
                new_steps.append(step)
                next_step_id += 1

                # Insert remediation step (Diagnose and fix)
                new_steps.append(
                    PlanStep(
                        step_id=next_step_id,
                        description=f"Diagnose and apply corrective fix for failure in step {step.step_id}: {error_message[:120]}",
                        tool_name="edit_file",
                        expected_output="Error diagnosed and code corrected",
                        status=StepStatus.PENDING,
                    )
                )
                next_step_id += 1

                # Insert test verification step
                new_steps.append(
                    PlanStep(
                        step_id=next_step_id,
                        description="Re-run test suite or verification to confirm fix",
                        tool_name="run_tests",
                        expected_output="All tests pass cleanly",
                        status=StepStatus.PENDING,
                    )
                )
                next_step_id += 1
            else:
                # Remaining future steps
                step.step_id = next_step_id
                new_steps.append(step)
                next_step_id += 1

        return Plan(
            task_id=plan.task_id,
            goal=plan.goal,
            steps=new_steps,
            created_at=datetime.now(timezone.utc),
            status=TaskStatus.RUNNING,
        )

    def _generate_heuristic_plan(self, task_id: str, goal: str, task_type: str) -> Plan:
        """Heuristic plan generation when LLM is unavailable or for standard workflows."""
        task_type_lower = task_type.lower()
        goal_lower = goal.lower()

        if "fix" in goal_lower or task_type_lower == "fix":
            steps = [
                PlanStep(
                    step_id=1,
                    description="Search and inspect target files related to the issue",
                    tool_name="search_code",
                    expected_output="Relevant source code locations identified",
                ),
                PlanStep(
                    step_id=2,
                    description="Read current file content and locate root cause",
                    tool_name="read_file",
                    expected_output="Root cause confirmed in code context",
                ),
                PlanStep(
                    step_id=3,
                    description="Apply targeted fix to resolve the issue",
                    tool_name="edit_file",
                    expected_output="Patch applied accurately",
                ),
                PlanStep(
                    step_id=4,
                    description="Run test suite to verify fix",
                    tool_name="run_tests",
                    expected_output="Tests pass with no regressions",
                ),
                PlanStep(
                    step_id=5,
                    description="Review git diff summary of changes",
                    tool_name="git_diff",
                    expected_output="Clean diff verified",
                ),
            ]
        elif "analyze" in goal_lower or "scan" in goal_lower or task_type_lower == "analysis":
            steps = [
                PlanStep(
                    step_id=1,
                    description="Scan repository structure and list key files",
                    tool_name="search_files",
                    arguments={"pattern": "**/*"},
                    expected_output="Repository file inventory compiled",
                ),
                PlanStep(
                    step_id=2,
                    description="Inspect repository status",
                    tool_name="git_status",
                    arguments={},
                    expected_output="Git status inspected",
                ),
                PlanStep(
                    step_id=3,
                    description="Search for main symbols and definitions",
                    tool_name="search_code",
                    arguments={"query": "def "},
                    expected_output="Key definitions located",
                ),
                PlanStep(
                    step_id=4,
                    description="Synthesize findings and generate analysis report",
                    expected_output="Comprehensive analysis report generated",
                ),
            ]
        else:
            # Standard development plan
            steps = [
                PlanStep(
                    step_id=1,
                    description="Search and locate relevant source files and modules",
                    tool_name="search_files",
                    arguments={"pattern": "**/*"},
                    expected_output="Target files identified",
                ),
                PlanStep(
                    step_id=2,
                    description="Search for existing definitions",
                    tool_name="search_code",
                    arguments={"query": "def "},
                    expected_output="Understanding of code structure",
                ),
                PlanStep(
                    step_id=3,
                    description="Verify workspace git status",
                    tool_name="git_status",
                    arguments={},
                    expected_output="Clean git working tree verified",
                ),
                PlanStep(
                    step_id=4,
                    description="Inspect git diff for modifications",
                    tool_name="git_diff",
                    arguments={},
                    expected_output="Diff verified ready for review",
                ),
            ]

        return Plan(
            task_id=task_id,
            goal=goal,
            steps=steps,
            created_at=datetime.now(timezone.utc),
            status=TaskStatus.PENDING,
        )

    def _generate_llm_plan(
        self,
        task_id: str,
        goal: str,
        repository_path: str,
        project_context: Optional[Dict[str, Any]],
    ) -> Optional[Plan]:
        """Ask LLM to generate a JSON step plan."""
        system_prompt = (
            "You are RepoLens Task Planner. Decompose the developer's goal into 3-6 ordered steps.\n"
            "Output ONLY a valid JSON array of objects with keys: 'description', 'tool_name', 'expected_output'.\n"
            "Available tools: read_file, write_file, edit_file, delete_file, search_files, search_code, run_command, run_tests, run_linter, git_status, git_diff, git_commit.\n"
            "Example:\n"
            '[{"description": "Search for auth routes", "tool_name": "search_code", "expected_output": "Auth routes located"}]'
        )

        user_prompt = f"Goal: {goal}\nRepository: {repository_path}"
        response = self.llm.generate(prompt=user_prompt, system_prompt=system_prompt)

        # Extract JSON array
        json_str = response.strip()
        if "```json" in json_str:
            json_str = json_str.split("```json")[1].split("```")[0].strip()
        elif "```" in json_str:
            json_str = json_str.split("```")[1].split("```")[0].strip()

        parsed = json.loads(json_str)
        if not isinstance(parsed, list):
            return None

        steps: List[PlanStep] = []
        for idx, item in enumerate(parsed, start=1):
            steps.append(
                PlanStep(
                    step_id=idx,
                    description=item.get("description", f"Step {idx}"),
                    tool_name=item.get("tool_name"),
                    expected_output=item.get("expected_output"),
                )
            )

        return Plan(
            task_id=task_id,
            goal=goal,
            steps=steps,
            created_at=datetime.now(timezone.utc),
            status=TaskStatus.PENDING,
        )
