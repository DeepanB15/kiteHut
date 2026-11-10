"""
Project Map Builder for RepoLens Context Engine.

Synthesizes structural repository layout, technology stack, discovered entry points,
detected architectural layers, and indexed symbols into a unified project map.
"""

from pathlib import Path
from typing import Any, Dict, List, Optional, Set
from pydantic import BaseModel, Field

from app.context.code.ast_analyzer import ASTCodeAnalyzer, CodeSymbol
from app.context.code.import_analyzer import ImportAnalyzer, ImportGraph
from app.context.code.symbol_index import SymbolIndex
from app.context.repository.repo_inspector import RepoInspector, RepoStructure
from app.context.repository.tech_detector import DetectedTech, TechDetector


class ArchitectureLayer(BaseModel):
    name: str  # api_layer, service_layer, data_layer, ui_layer, test_layer, config_layer
    description: str
    files: List[str] = Field(default_factory=list)
    key_symbols: List[str] = Field(default_factory=list)


class ProjectMap(BaseModel):
    repository_path: str
    structure: RepoStructure
    technologies: List[DetectedTech] = Field(default_factory=list)
    entry_points: List[str] = Field(default_factory=list)
    layers: List[ArchitectureLayer] = Field(default_factory=list)
    symbol_summary: Dict[str, int] = Field(default_factory=dict)
    circular_dependencies: List[str] = Field(default_factory=list)
    external_packages: List[str] = Field(default_factory=list)


class ProjectMapBuilder:
    """Builds comprehensive ProjectMap for repository intelligence."""

    def __init__(self, root_path: str):
        self.root_path = Path(root_path).resolve()

    def build(self) -> tuple[ProjectMap, SymbolIndex, ImportGraph]:
        """Inspect repository and construct ProjectMap, SymbolIndex, and ImportGraph."""
        # 1. Inspect repository layout
        inspector = RepoInspector(str(self.root_path))
        structure = inspector.inspect()

        # 2. Detect technologies and entry points
        tech_detector = TechDetector(str(self.root_path))
        technologies = tech_detector.detect()
        entry_points = tech_detector.find_entry_points()

        # 3. Read source files and build AST symbol index
        ast_analyzer = ASTCodeAnalyzer()
        all_symbols: List[CodeSymbol] = []
        file_contents: Dict[str, str] = {}

        # Scan text files up to 500KB
        for finfo in structure.file_inventory:
            if finfo.language in ("Python", "JavaScript", "TypeScript", "Go", "Java"):
                fpath = self.root_path / finfo.relative_path
                try:
                    content = fpath.read_text(encoding="utf-8", errors="ignore")
                    file_contents[finfo.relative_path] = content
                    syms = ast_analyzer.parse_file(finfo.relative_path, content)
                    all_symbols.extend(syms)
                except Exception:
                    continue

        symbol_index = SymbolIndex(symbols=all_symbols)

        # 4. Build Import Graph & detect circular dependencies
        import_analyzer = ImportAnalyzer(str(self.root_path))
        import_graph = import_analyzer.build_graph(file_contents)

        # 5. Classify Architecture Layers
        layers = self._classify_layers(structure, symbol_index)

        project_map = ProjectMap(
            repository_path=str(self.root_path),
            structure=structure,
            technologies=technologies,
            entry_points=entry_points,
            layers=layers,
            symbol_summary=symbol_index.get_summary(),
            circular_dependencies=[c.description for c in import_graph.circular_dependencies],
            external_packages=sorted(list(import_graph.external_packages)),
        )

        return project_map, symbol_index, import_graph

    def _classify_layers(self, structure: RepoStructure, symbol_index: SymbolIndex) -> List[ArchitectureLayer]:
        """Segment codebase into standard architectural tiers."""
        layer_buckets: Dict[str, Dict[str, Any]] = {
            "api_layer": {
                "name": "API & Presentation Layer",
                "description": "HTTP routes, controllers, endpoints, and request handlers",
                "files": [],
                "symbols": [],
            },
            "service_layer": {
                "name": "Business Logic & Services",
                "description": "Core workflows, domain services, orchestration logic",
                "files": [],
                "symbols": [],
            },
            "data_layer": {
                "name": "Data Access & Models",
                "description": "Database schemas, ORM models, repositories, and persistence",
                "files": [],
                "symbols": [],
            },
            "test_layer": {
                "name": "Test Suites",
                "description": "Unit, integration, and e2e test fixtures",
                "files": [],
                "symbols": [],
            },
            "config_layer": {
                "name": "Configuration & Infrastructure",
                "description": "Settings, environment variables, docker, and devops manifests",
                "files": [],
                "symbols": [],
            },
        }

        for finfo in structure.file_inventory:
            rel = finfo.relative_path.lower()

            if "test" in rel:
                layer_buckets["test_layer"]["files"].append(finfo.relative_path)
            elif any(k in rel for k in ("api", "route", "controller", "endpoint")):
                layer_buckets["api_layer"]["files"].append(finfo.relative_path)
            elif any(k in rel for k in ("model", "schema", "db", "repository", "entity", "migration")):
                layer_buckets["data_layer"]["files"].append(finfo.relative_path)
            elif any(k in rel for k in ("service", "agent", "engine", "handler", "manager", "core")):
                layer_buckets["service_layer"]["files"].append(finfo.relative_path)
            elif any(k in rel for k in ("config", "setting", "docker", ".env", "manifest")):
                layer_buckets["config_layer"]["files"].append(finfo.relative_path)

        # Collect symbols for each layer
        for sym in symbol_index.symbols:
            rel = sym.file_path.lower()
            if any(k in rel for k in ("api", "route")):
                if len(layer_buckets["api_layer"]["symbols"]) < 20:
                    layer_buckets["api_layer"]["symbols"].append(f"{sym.name} ({sym.file_path}:{sym.start_line})")
            elif any(k in rel for k in ("service", "engine", "agent")):
                if len(layer_buckets["service_layer"]["symbols"]) < 20:
                    layer_buckets["service_layer"]["symbols"].append(f"{sym.name} ({sym.file_path}:{sym.start_line})")
            elif any(k in rel for k in ("model", "schema")):
                if len(layer_buckets["data_layer"]["symbols"]) < 20:
                    layer_buckets["data_layer"]["symbols"].append(f"{sym.name} ({sym.file_path}:{sym.start_line})")

        layers: List[ArchitectureLayer] = []
        for lkey, ldata in layer_buckets.items():
            if ldata["files"]:
                layers.append(
                    ArchitectureLayer(
                        name=ldata["name"],
                        description=ldata["description"],
                        files=ldata["files"][:50],
                        key_symbols=ldata["symbols"],
                    )
                )

        return layers
