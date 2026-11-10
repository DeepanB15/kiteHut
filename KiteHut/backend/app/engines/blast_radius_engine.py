"""
Blast Radius Engine.

Analyzes what parts of the application could be affected by a finding.
Uses static analysis of file relationships and imports.

Deterministic and static-analysis-based. No paid APIs needed.
"""

from pathlib import Path
from typing import List
from collections import defaultdict

from app.models.scored_finding import ScoredFinding
from app.models.blast_radius import BlastRadius


def analyze_blast_radius(
    scored_findings: List[ScoredFinding],
    repository_path: str,
) -> List[BlastRadius]:
    """
    Analyze blast radius for each finding based on file relationships.
    """
    # Build a dependency graph from the repository
    dep_graph = _build_dependency_graph(repository_path)

    results = []
    for sf in scored_findings:
        radius = _calculate_radius(sf, dep_graph, repository_path)
        results.append(radius)

    print(f"  [BlastRadiusEngine] Analyzed {len(results)} blast radii.")

    return results


def _build_dependency_graph(repository_path: str) -> dict[str, set[str]]:
    """
    Build a simple dependency graph from import statements.
    Returns: {file: set of files that import it}
    """
    repo = Path(repository_path)
    graph = defaultdict(set)
    file_map = {}  # module_name -> file_path

    # First pass: map module names to files
    for py_file in repo.rglob("*.py"):
        if _should_skip(py_file, repo):
            continue
        relative = py_file.relative_to(repo)
        module = str(relative.with_suffix("")).replace("\\", "/").replace("/", ".")
        file_map[module] = str(relative)
        # Also map just the filename
        file_map[py_file.name] = str(relative)

    # Second pass: parse imports
    for py_file in repo.rglob("*.py"):
        if _should_skip(py_file, repo):
            continue
        relative = str(py_file.relative_to(repo))

        try:
            content = py_file.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue

        for line in content.splitlines():
            line = line.strip()
            # from X import Y
            if line.startswith("from ") and " import " in line:
                module = line.split("from ")[1].split(" import ")[0].strip()
                if module in file_map:
                    graph[file_map[module]].add(relative)
            # import X
            elif line.startswith("import ") and not line.startswith("import("):
                module = line.split("import ")[1].split(".")[0].strip()
                if module in file_map:
                    graph[file_map[module]].add(relative)

    return dict(graph)


def _calculate_radius(
    finding: ScoredFinding,
    dep_graph: dict[str, set[str]],
    repository_path: str,
) -> BlastRadius:
    """Calculate blast radius for a single finding."""
    repo = Path(repository_path)

    # Try to find files related to the finding
    affected_files = _find_related_files(finding, repo)

    # Find dependent files
    dependent_files = set()
    for af in affected_files:
        if af in dep_graph:
            dependent_files.update(dep_graph[af])

    # Reverse dependencies: files that the affected files import
    reverse_deps = set()
    for module, dependents in dep_graph.items():
        if module in affected_files:
            reverse_deps.update(dependents)

    all_affected = affected_files + list(dependent_files) + list(reverse_deps)
    total = len(set(all_affected))

    # Determine radius level
    if total >= 10:
        level = "CRITICAL"
        scope = "system"
    elif total >= 5:
        level = "HIGH"
        scope = "package"
    elif total >= 2:
        level = "MEDIUM"
        scope = "module"
    else:
        level = "LOW"
        scope = "local"

    # Build modules list
    modules = set()
    for f in all_affected:
        parts = Path(f).parts
        if len(parts) > 1:
            modules.add(parts[0])

    description = _build_description(finding, total, level, scope)

    return BlastRadius(
        finding_id=finding.finding_id,
        affected_files=list(set(affected_files))[:20],
        affected_modules=list(modules)[:10],
        dependent_files=list(dependent_files)[:20],
        radius_level=level,
        scope=scope,
        total_affected=total,
        description=description,
    )


def _find_related_files(finding: ScoredFinding, repo: Path) -> list[str]:
    """Find files related to a finding based on claim type and statement."""
    related = []

    # Keywords to search for based on claim type
    keywords = _get_keywords_for_type(finding.claim_type)

    for py_file in repo.rglob("*"):
        if _should_skip(py_file, repo):
            continue
        if not py_file.is_file():
            continue

        relative = str(py_file.relative_to(repo))

        # Check filename
        name_lower = py_file.name.lower()
        for kw in keywords:
            if kw in name_lower:
                related.append(relative)
                break

        # Check content for keywords (only for source files)
        if py_file.suffix in {".py", ".js", ".ts"} and len(related) < 10:
            try:
                content = py_file.read_text(encoding="utf-8", errors="ignore").lower()
                for kw in keywords:
                    if kw in content:
                        related.append(relative)
                        break
            except Exception:
                pass

    return list(set(related))[:15]


def _get_keywords_for_type(claim_type: str) -> list[str]:
    """Get relevant keywords for a claim type."""
    mapping = {
        "hardcoded_secret": ["config", "secret", "key", "env", "credential"],
        "missing_authentication": ["auth", "login", "middleware", "token"],
        "missing_authorization": ["auth", "permission", "role", "access"],
        "missing_tests": ["test", "spec"],
        "poor_error_handling": ["error", "exception", "handler"],
        "tight_coupling": ["import", "service", "repository"],
        "code_duplication": ["util", "helper", "common"],
        "large_function": [],
        "large_class": [],
        "layer_violation": ["route", "controller", "service", "model"],
        "weak_input_validation": ["valid", "sanitiz", "input"],
        "debug_mode_enabled": ["config", "settings", "env"],
        "missing_test_framework": ["test", "spec", "jest", "pytest"],
    }
    return mapping.get(claim_type, [])


def _should_skip(path: Path, repo: Path) -> bool:
    """Check if path should be skipped."""
    skip = {".git", "node_modules", ".venv", "venv", "__pycache__", ".next", "dist", "build"}
    try:
        relative = path.relative_to(repo)
        return any(part in skip for part in relative.parts)
    except ValueError:
        return True


def _build_description(finding: ScoredFinding, total: int, level: str, scope: str) -> str:
    """Build human-readable blast radius description."""
    ct = finding.claim_type.replace("_", " ")
    if total <= 1:
        return f"This {ct} issue is localized to a single file."
    elif total <= 4:
        return f"This {ct} issue may affect {total} files across {scope} scope."
    else:
        return f"This {ct} issue has a {level.lower()} blast radius, potentially affecting {total} files."
