"""
Missing PRD Phase 2 named tools for RepoLens.

Implements:
- list_files
- find_symbol
- get_repo_structure
- get_dependencies
- get_git_diff (PRD name; tool already registered as git_diff)
- get_git_log (PRD name; tool already registered as git_log)
- run_analysis
"""

from pathlib import Path
from typing import Any, Dict, List, Optional

from app.agent.permissions.policies import PermissionType, RiskLevel
from app.context.project_map.project_map import ProjectMapBuilder
from app.context.repository.repo_inspector import RepoInspector
from app.context.repository.tech_detector import TechDetector
from app.context.code.symbol_index import SymbolIndex
from app.context.code.ast_analyzer import ASTCodeAnalyzer, SymbolType
from app.tools.base import BaseTool
from app.tools.sandbox import PathValidator


class ListFilesTool(BaseTool):
    """List files and directories in the repository."""

    name = "list_files"
    description = "List directory contents or repository file inventory with optional filtering."
    permission_type = PermissionType.READ
    risk_level = RiskLevel.SAFE

    def get_parameter_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Subdirectory path relative to repository root (default '.')",
                },
                "pattern": {
                    "type": "string",
                    "description": "Optional glob filter (e.g., '*.py')",
                },
                "repository_path": {
                    "type": "string",
                    "description": "Root workspace repository path",
                },
            },
            "required": ["repository_path"],
        }

    def run(
        self,
        repository_path: str,
        path: str = ".",
        pattern: Optional[str] = None,
        **kwargs,
    ) -> str:
        base_dir = PathValidator.resolve_safe_path(path, repository_path)
        if not base_dir.exists():
            raise FileNotFoundError(f"Directory not found: {path}")
        entries = []
        if pattern:
            for p in base_dir.rglob(pattern):
                try:
                    rel = p.relative_to(Path(repository_path).resolve())
                    entries.append(str(rel).replace("\\", "/"))
                except ValueError:
                    continue
        else:
            try:
                for item in sorted(base_dir.iterdir()):
                    rel = item.relative_to(Path(repository_path).resolve())
                    entries.append(("/" if item.is_dir() else "  ") + str(rel).replace("\\", "/"))
            except Exception as e:
                raise RuntimeError(f"Failed to list directory: {e}")
        entries.sort()
        if not entries:
            return f"No entries in '{path}'"
        return f"=== List: {path} ===\n" + "\n".join(entries[:200])


class FindSymbolTool(BaseTool):
    """Find a symbol by name or partial match in the repository."""

    name = "find_symbol"
    description = "Search for a code symbol (function, class, variable) by name or substring."
    permission_type = PermissionType.READ
    risk_level = RiskLevel.SAFE

    def get_parameter_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Symbol name or substring to search for",
                },
                "repository_path": {
                    "type": "string",
                    "description": "Root workspace repository path",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum results (default 10)",
                },
            },
            "required": ["query", "repository_path"],
        }

    def run(
        self,
        query: str,
        repository_path: str,
        limit: int = 10,
        **kwargs,
    ) -> str:
        from app.context.project_map.project_map import ProjectMapBuilder
        builder = ProjectMapBuilder(str(Path(repository_path).resolve()))
        _, symbol_index, _ = builder.build()
        results = symbol_index.search_symbols(query, limit=limit)
        if not results:
            return f"No symbols found for '{query}'"
        lines = [
            f"{sym.name}  ({sym.file_path}:{sym.start_line})  [{sym.symbol_type.value}]"
            for sym in results
        ]
        return f"=== Symbol Search: '{query}' ===\n" + "\n".join(lines[:limit])


class GetRepoStructureTool(BaseTool):
    """Get repository structure (file inventory + technologies + layers)."""

    name = "get_repo_structure"
    description = "Get structural overview of the repository: files, technologies, layers, entry points."
    permission_type = PermissionType.READ
    risk_level = RiskLevel.SAFE

    def get_parameter_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "repository_path": {
                    "type": "string",
                    "description": "Root workspace repository path",
                },
                "include_symbols": {
                    "type": "boolean",
                    "description": "Include symbol counts",
                },
            },
            "required": ["repository_path"],
        }

    def run(
        self,
        repository_path: str,
        include_symbols: bool = False,
        **kwargs,
    ) -> str:
        builder = ProjectMapBuilder(str(Path(repository_path).resolve()))
        project_map, symbol_index, _ = builder.build()
        lines = [
            f"Repository: {project_map.repository_path}",
            f"Files scanned: {len(project_map.structure.file_inventory)}",
            f"Technologies: {', '.join(t.name for t in project_map.technologies) if project_map.technologies else 'none detected'}",
            f"Entry points: {', '.join(project_map.entry_points) if project_map.entry_points else 'none'}",
            f"Layers: {', '.join(l.name for l in project_map.layers) if project_map.layers else 'none'}",
        ]
        if include_symbols:
            lines.append(f"Symbols: {symbol_index.get_summary()}")
        return "=== Repository Structure ===\n" + "\n".join(lines)


class GetDependenciesTool(BaseTool):
    """Get detected external dependencies/packages for the repository."""

    name = "get_dependencies"
    description = "List external package dependencies detected from manifests."
    permission_type = PermissionType.READ
    risk_level = RiskLevel.SAFE

    def get_parameter_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "repository_path": {
                    "type": "string",
                    "description": "Root workspace repository path",
                },
            },
            "required": ["repository_path"],
        }

    def run(self, repository_path: str, **kwargs) -> str:
        builder = ProjectMapBuilder(str(Path(repository_path).resolve()))
        project_map, _, _ = builder.build()
        deps = sorted(project_map.external_packages)
        if not deps:
            return "No external dependencies detected."
        return "=== Dependencies ===\n" + "\n".join(deps[:200])


class RunAnalysisTool(BaseTool):
    """Run repository analysis (security, quality, architecture, testing)."""

    name = "run_analysis"
    description = "Run multi-agent repository analysis and return findings summary."
    permission_type = PermissionType.READ
    risk_level = RiskLevel.SAFE

    def get_parameter_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "repository_path": {
                    "type": "string",
                    "description": "Root workspace repository path",
                },
                "categories": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Categories to analyze (security, quality, architecture, testing, config, dependency)",
                },
            },
            "required": ["repository_path"],
        }

    def run(
        self,
        repository_path: str,
        categories: Optional[List[str]] = None,
        **kwargs,
    ) -> str:
        # Delegate to existing intelligence orchestrator if available
        try:
            from app.intelligence.orchestrator.orchestrator import run_analysis
            result = run_analysis(str(Path(repository_path).resolve()), categories or ["security", "quality"])
            findings = result.get("findings", []) if isinstance(result, dict) else []
            if not findings and isinstance(result, list):
                findings = result
            if isinstance(findings, list) and findings:
                summary = f"Found {len(findings)} finding(s)\n" + "\n".join(
                    f"- [{f.get('severity', '?')}] {f.get('title', f.get('category', 'finding'))}" for f in findings[:10]
                )
            else:
                summary = "Analysis complete — no findings reported."
            return f"=== Analysis Result ===\n{summary}"
        except Exception as e:
            # Fallback deterministic summary
            return f"=== Analysis (fallback) ===\nRepository: {repository_path}\nCategories: {categories or ['default']}\nStatus: analysis delegate unavailable ({e}). Use agent intelligence commands for full review."


# PRD-named aliases for existing git tools
# These are wrapped as alias tools so both names work
class GetGitDiffTool(BaseTool):
    name = "get_git_diff"
    description = "Alias for git_diff (view git diffs)."
    permission_type = PermissionType.GIT
    risk_level = RiskLevel.SAFE

    def get_parameter_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "repository_path": {"type": "string"},
                "file_path": {"type": "string"},
                "staged": {"type": "boolean"},
            },
            "required": ["repository_path"],
        }

    def run(self, repository_path: str, file_path: Optional[str] = None, staged: bool = False, **kwargs) -> str:
        from app.tools.git_tools import GitDiffTool
        return GitDiffTool().run(repository_path=repository_path, file_path=file_path, staged=staged)


class GetGitLogTool(BaseTool):
    name = "get_git_log"
    description = "Alias for git_log (view recent git commits)."
    permission_type = PermissionType.GIT
    risk_level = RiskLevel.SAFE

    def get_parameter_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "repository_path": {"type": "string"},
                "max_count": {"type": "integer"},
            },
            "required": ["repository_path"],
        }

    def run(self, repository_path: str, max_count: int = 10, **kwargs) -> str:
        from app.tools.git_tools import GitLogTool
        return GitLogTool().run(repository_path=repository_path, max_count=max_count)
