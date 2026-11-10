"""
Import Graph and Circular Dependency Analyzer for RepoLens Context Engine.

Extracts internal module imports and external package dependencies across source files,
builds directed module dependency graphs, and discovers circular dependency cycles.
"""

import ast
from pathlib import Path
import re
from typing import Any, Dict, List, Optional, Set, Tuple
from pydantic import BaseModel, Field


class ImportStatement(BaseModel):
    source_file: str
    imported_module: str
    imported_symbols: List[str] = Field(default_factory=list)
    is_relative: bool = False
    level: int = 0
    line_number: int = 1
    is_external: bool = False


class CircularDependency(BaseModel):
    cycle: List[str]  # e.g. ["app/service.py", "app/database.py", "app/service.py"]
    description: str


class ImportGraph(BaseModel):
    modules: List[str] = Field(default_factory=list)
    # Mapping: source_module -> list of imported target_modules
    dependencies: Dict[str, List[str]] = Field(default_factory=dict)
    # Mapping: target_module -> list of dependent source_modules
    dependents: Dict[str, List[str]] = Field(default_factory=dict)
    external_packages: Set[str] = Field(default_factory=set)
    circular_dependencies: List[CircularDependency] = Field(default_factory=list)


class ImportAnalyzer:
    """Analyzes imports across repository files and constructs the dependency graph."""

    def __init__(self, root_path: str):
        self.root_path = Path(root_path).resolve()

    def parse_python_imports(self, file_path: str, content: str) -> List[ImportStatement]:
        """Extract all import statements from Python source."""
        norm_file = file_path.replace("\\", "/")
        imports: List[ImportStatement] = []

        try:
            tree = ast.parse(content)
        except Exception:
            return self._parse_regex_imports(norm_file, content)

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append(
                        ImportStatement(
                            source_file=norm_file,
                            imported_module=alias.name,
                            imported_symbols=[alias.asname or alias.name],
                            is_relative=False,
                            line_number=node.lineno,
                            is_external=self._is_external_python_pkg(alias.name),
                        )
                    )
            elif isinstance(node, ast.ImportFrom):
                mod_name = node.module or ""
                symbols = [alias.name for alias in node.names]
                is_rel = (node.level or 0) > 0
                imports.append(
                    ImportStatement(
                        source_file=norm_file,
                        imported_module=mod_name,
                        imported_symbols=symbols,
                        is_relative=is_rel,
                        level=node.level or 0,
                        line_number=node.lineno,
                        is_external=not is_rel and self._is_external_python_pkg(mod_name),
                    )
                )

        return imports

    def _parse_regex_imports(self, file_path: str, content: str) -> List[ImportStatement]:
        """Fallback regex parser for imports (Python/JS/TS)."""
        imports: List[ImportStatement] = []
        lines = content.splitlines()

        # JS/TS import: import { a } from './b'; or import * as c from 'pkg'
        js_import = re.compile(r"""(?:import\s+.*?\s+from\s+['"](.*?)['"])|(?:require\(['"](.*?)['"]\))""")
        # Python import: from x import y or import z
        py_from = re.compile(r"""from\s+([a-zA-Z0-9_.]+)\s+import\s+(.*)""")
        py_import = re.compile(r"""import\s+([a-zA-Z0-9_.]+)""")

        for i, line in enumerate(lines, start=1):
            s = line.strip()
            # JS/TS
            jm = js_import.search(s)
            if jm:
                target = jm.group(1) or jm.group(2)
                is_rel = target.startswith(".")
                imports.append(
                    ImportStatement(
                        source_file=file_path,
                        imported_module=target,
                        is_relative=is_rel,
                        line_number=i,
                        is_external=not is_rel,
                    )
                )
                continue

            # Python
            pm = py_from.match(s)
            if pm:
                mod = pm.group(1)
                syms = [sym.strip() for sym in pm.group(2).split(",")]
                imports.append(
                    ImportStatement(
                        source_file=file_path,
                        imported_module=mod,
                        imported_symbols=syms,
                        is_relative=mod.startswith("."),
                        line_number=i,
                        is_external=not mod.startswith(".") and self._is_external_python_pkg(mod),
                    )
                )
                continue

            pim = py_import.match(s)
            if pim:
                mod = pim.group(1)
                imports.append(
                    ImportStatement(
                        source_file=file_path,
                        imported_module=mod,
                        is_relative=False,
                        line_number=i,
                        is_external=self._is_external_python_pkg(mod),
                    )
                )

        return imports

    def build_graph(self, file_contents: Dict[str, str]) -> ImportGraph:
        """Construct full dependency graph and find circular loops."""
        dependencies: Dict[str, Set[str]] = {}
        dependents: Dict[str, Set[str]] = {}
        all_modules: Set[str] = set()
        external_pkgs: Set[str] = set()

        for fpath, content in file_contents.items():
            norm_path = fpath.replace("\\", "/")
            all_modules.add(norm_path)
            if norm_path not in dependencies:
                dependencies[norm_path] = set()
            if norm_path not in dependents:
                dependents[norm_path] = set()

            ext = Path(norm_path).suffix.lower()
            if ext == ".py":
                stmts = self.parse_python_imports(norm_path, content)
            else:
                stmts = self._parse_regex_imports(norm_path, content)

            for stmt in stmts:
                if stmt.is_external:
                    external_pkgs.add(stmt.imported_module.split(".")[0])
                else:
                    # Resolve relative or internal module path
                    target_file = self._resolve_internal_import(norm_path, stmt, file_contents.keys())
                    if target_file and target_file != norm_path:
                        dependencies[norm_path].add(target_file)
                        if target_file not in dependents:
                            dependents[target_file] = set()
                        dependents[target_file].add(norm_path)

        # Detect circular dependencies using DFS cycle detection
        cycles = self._find_cycles(dependencies)

        return ImportGraph(
            modules=sorted(list(all_modules)),
            dependencies={k: sorted(list(v)) for k, v in dependencies.items()},
            dependents={k: sorted(list(v)) for k, v in dependents.items()},
            external_packages=external_pkgs,
            circular_dependencies=cycles,
        )

    def _resolve_internal_import(
        self,
        source_file: str,
        stmt: ImportStatement,
        known_files: Any,
    ) -> Optional[str]:
        """Resolve an import statement to a known relative file in the workspace."""
        known_set = {f.replace("\\", "/") for f in known_files}
        source_p = Path(source_file)

        if stmt.is_relative:
            base_dir = source_p.parent
            for _ in range(max(0, stmt.level - 1)):
                base_dir = base_dir.parent

            # Candidate paths
            if stmt.imported_module:
                sub_path = stmt.imported_module.replace(".", "/")
                cand = (base_dir / sub_path).as_posix()
            else:
                cand = base_dir.as_posix()

            for ext in (".py", ".ts", ".js", ".tsx", "/__init__.py", "/index.ts"):
                t = (cand + ext).lstrip("./")
                if t in known_set:
                    return t
        else:
            # Internal absolute import e.g. "app.services.auth"
            mod_path = stmt.imported_module.replace(".", "/")
            for ext in (".py", ".ts", ".js", "/__init__.py", "/index.ts", ""):
                t = (mod_path + ext).lstrip("./")
                if t in known_set:
                    return t

        return None

    def _is_external_python_pkg(self, mod_name: str) -> bool:
        """Check if Python module is part of standard library or external package."""
        top_pkg = mod_name.split(".")[0]
        # Standard library or common root names
        stdlib = {
            "os", "sys", "re", "json", "typing", "collections", "pathlib",
            "datetime", "time", "subprocess", "logging", "math", "random",
            "shutil", "tempfile", "unittest", "hashlib", "urllib", "uuid",
            "ast", "io", "copy", "itertools", "functools", "dataclasses",
        }
        return top_pkg in stdlib or not (self.root_path / top_pkg).exists()

    def _find_cycles(self, adj: Dict[str, Set[str]]) -> List[CircularDependency]:
        """Find circular dependency cycles via DFS."""
        visited: Dict[str, int] = {}  # 0: unvisited, 1: visiting, 2: visited
        cycles: List[CircularDependency] = []

        def dfs(node: str, path: List[str]):
            visited[node] = 1
            path.append(node)

            for neighbor in adj.get(node, []):
                if visited.get(neighbor) == 1:
                    # Found cycle
                    cycle_start = path.index(neighbor)
                    cycle_nodes = path[cycle_start:] + [neighbor]
                    cycles.append(
                        CircularDependency(
                            cycle=cycle_nodes,
                            description=f"Circular dependency loop: {' -> '.join(cycle_nodes)}",
                        )
                    )
                elif visited.get(neighbor, 0) == 0:
                    dfs(neighbor, path)

            path.pop()
            visited[node] = 2

        for node in list(adj.keys()):
            if visited.get(node, 0) == 0:
                dfs(node, [])

        return cycles
