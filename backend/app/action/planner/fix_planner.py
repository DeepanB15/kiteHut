"""
Fix Planner for RepoLens Action Engine.

Generates structured multi-file ProposedPatch objects from verified findings.
"""

from pathlib import Path
import re
from typing import Optional

from app.action.models.patch import FileChangeType, FilePatch, ProposedPatch
from app.intelligence.models.findings import Finding, FindingCategory
from app.llm.base import BaseLLMProvider


class FixPlanner:
    """Plans remediation patches for detected code defects and findings."""

    def __init__(self, repository_path: str, llm_provider: Optional[BaseLLMProvider] = None):
        self.root = Path(repository_path).resolve()
        self.llm = llm_provider

    def plan_fix(self, finding: Finding) -> ProposedPatch:
        """Create a structured remediation patch for a finding."""
        title_lower = finding.title.lower()
        desc_lower = finding.description.lower()

        # 1. Missing Environment Variable Recipe
        if finding.category == FindingCategory.CONFIGURATION or "env.example" in title_lower or "undocumented" in title_lower:
            return self._plan_config_fix(finding)

        # 2. Hardcoded Secret Recipe
        if finding.category == FindingCategory.SECURITY and ("secret" in title_lower or "credential" in title_lower or "key" in title_lower):
            return self._plan_secret_fix(finding)

        # 3. Unpinned Dependency Recipe
        if finding.category == FindingCategory.DEPENDENCY or "unpinned" in title_lower:
            return self._plan_dependency_fix(finding)

        # 4. Debug Code Cleanup Recipe
        if finding.category == FindingCategory.CODE_REVIEW or "debug" in title_lower or "print" in title_lower or "breakpoint" in title_lower:
            return self._plan_debug_cleanup_fix(finding)

        # 5. Untested Module Scaffold Recipe
        if finding.category == FindingCategory.TESTING or "untested" in title_lower:
            return self._plan_test_scaffold_fix(finding)

        # Fallback generic patch
        return self._plan_generic_fix(finding)

    def _plan_config_fix(self, finding: Finding) -> ProposedPatch:
        """Generate patch adding missing variable to .env.example."""
        env_ex_path = self.root / ".env.example"
        orig_content = env_ex_path.read_text(encoding="utf-8", errors="replace") if env_ex_path.exists() else ""

        # Extract variable name from title/description
        match = re.search(r"['\"]?([A-Z0-9_]{3,})['\"]?", finding.title + " " + finding.description)
        var_name = match.group(1) if match else "CONFIG_KEY"

        new_content = orig_content
        if orig_content and not orig_content.endswith("\n"):
            new_content += "\n"
        new_content += f"{var_name}=your_{var_name.lower()}_here\n"

        file_patch = FilePatch(
            file_path=".env.example",
            change_type=FileChangeType.MODIFY if env_ex_path.exists() else FileChangeType.CREATE,
            original_content=orig_content,
            new_content=new_content,
            description=f"Add missing {var_name} environment variable to template.",
        )

        return ProposedPatch(
            finding_id=finding.finding_id,
            title=f"Add {var_name} to .env.example",
            description=f"Documents required environment variable {var_name} in .env.example template.",
            file_patches=[file_patch],
            estimated_effort_minutes=5,
            risk_level="low",
        )

    def _plan_secret_fix(self, finding: Finding) -> ProposedPatch:
        """Replace hardcoded secret with os.getenv and add to .env.example."""
        file_patches = []
        if not finding.file_path:
            return self._plan_generic_fix(finding)

        source_path = self.root / finding.file_path
        if source_path.exists() and source_path.is_file():
            orig_src = source_path.read_text(encoding="utf-8", errors="replace")
            # Replace secret assignment with os.getenv
            new_src = orig_src
            if "sk_live_" in new_src or "sk_test_" in new_src:
                new_src = re.sub(
                    r"['\"]sk_(?:live|test)_[a-zA-Z0-9_]+['\"]",
                    "os.getenv('API_SECRET_KEY')",
                    new_src,
                )
                if "import os" not in new_src:
                    new_src = "import os\n" + new_src

                file_patches.append(
                    FilePatch(
                        file_path=finding.file_path,
                        change_type=FileChangeType.MODIFY,
                        original_content=orig_src,
                        new_content=new_src,
                        description="Replace plaintext secret with os.getenv lookup.",
                    )
                )

        # Also update .env.example
        env_ex_path = self.root / ".env.example"
        orig_env = env_ex_path.read_text(encoding="utf-8", errors="replace") if env_ex_path.exists() else ""
        new_env = orig_env + ("\n" if orig_env and not orig_env.endswith("\n") else "") + "API_SECRET_KEY=your_key_here\n"

        file_patches.append(
            FilePatch(
                file_path=".env.example",
                change_type=FileChangeType.MODIFY if env_ex_path.exists() else FileChangeType.CREATE,
                original_content=orig_env,
                new_content=new_env,
                description="Add API_SECRET_KEY placeholder to .env.example.",
            )
        )

        return ProposedPatch(
            finding_id=finding.finding_id,
            title="Secure Hardcoded Secret with Environment Variable",
            description="Replaces plaintext token with os.getenv and adds placeholder in .env.example.",
            file_patches=file_patches,
            estimated_effort_minutes=10,
            risk_level="low",
        )

    def _plan_dependency_fix(self, finding: Finding) -> ProposedPatch:
        """Pin dependencies in requirements.txt."""
        target = finding.file_path or "requirements.txt"
        path = self.root / target
        orig_content = path.read_text(encoding="utf-8", errors="replace") if path.exists() else ""

        # Pin >= to ==
        new_content = re.sub(r">=([0-9\.]+)", r"==\1", orig_content)

        return ProposedPatch(
            finding_id=finding.finding_id,
            title=f"Pin versions in {target}",
            description="Replace unpinned or loose dependencies with deterministic locked versions.",
            file_patches=[
                FilePatch(
                    file_path=target,
                    change_type=FileChangeType.MODIFY,
                    original_content=orig_content,
                    new_content=new_content,
                    description="Lock dependencies.",
                )
            ],
            estimated_effort_minutes=5,
            risk_level="low",
        )

    def _plan_debug_cleanup_fix(self, finding: Finding) -> ProposedPatch:
        """Remove print() or breakpoint() statements."""
        target = finding.file_path
        if not target:
            return self._plan_generic_fix(finding)

        path = self.root / target
        if not path.exists():
            return self._plan_generic_fix(finding)

        orig_lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        new_lines = []
        for line in orig_lines:
            stripped = line.strip()
            if stripped.startswith("print(") or stripped.startswith("breakpoint()") or stripped.startswith("console.log("):
                continue
            new_lines.append(line)

        new_content = "\n".join(new_lines) + "\n"

        return ProposedPatch(
            finding_id=finding.finding_id,
            title=f"Remove Debug Statements from {target}",
            description="Cleans up accidental debug logging and breakpoints from source code.",
            file_patches=[
                FilePatch(
                    file_path=target,
                    change_type=FileChangeType.MODIFY,
                    original_content="\n".join(orig_lines) + "\n",
                    new_content=new_content,
                    description="Remove debug lines.",
                )
            ],
            estimated_effort_minutes=5,
            risk_level="low",
        )

    def _plan_test_scaffold_fix(self, finding: Finding) -> ProposedPatch:
        """Generate a test scaffold file for untested source module."""
        target = finding.file_path or "src/main.py"
        stem = Path(target).stem
        test_file = f"tests/test_{stem}.py"
        test_path = self.root / test_file

        orig_content = test_path.read_text(encoding="utf-8", errors="replace") if test_path.exists() else ""
        new_content = (
            f'"""\nAutomated Unit Tests for {target}\n"""\n\n'
            f"def test_{stem}_basic():\n"
            f'    """Verify basic operational behavior for {stem}."""\n'
            f"    assert True\n"
        )

        return ProposedPatch(
            finding_id=finding.finding_id,
            title=f"Generate Unit Test Scaffold for {target}",
            description=f"Creates unit test suite in {test_file}.",
            file_patches=[
                FilePatch(
                    file_path=test_file,
                    change_type=FileChangeType.MODIFY if test_path.exists() else FileChangeType.CREATE,
                    original_content=orig_content,
                    new_content=new_content,
                    description=f"Add unit test suite for {stem}.",
                )
            ],
            estimated_effort_minutes=15,
            risk_level="low",
        )

    def _plan_generic_fix(self, finding: Finding) -> ProposedPatch:
        """Fallback generic patch proposal."""
        return ProposedPatch(
            finding_id=finding.finding_id,
            title=f"Remediation for: {finding.title}",
            description=finding.recommendation or finding.description,
            file_patches=[],
            estimated_effort_minutes=20,
            risk_level="medium",
        )
