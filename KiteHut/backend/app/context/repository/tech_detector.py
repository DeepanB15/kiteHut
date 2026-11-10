"""
Technology Stack and Framework Detector for RepoLens Context Engine.

Analyzes dependency manifests, configuration files, and code signatures to identify
languages, frameworks, test suites, ORMs, and container tooling.
"""

from pathlib import Path
from typing import Dict, List, Optional, Set
from pydantic import BaseModel, Field


class DetectedTech(BaseModel):
    name: str
    category: str  # backend_framework, frontend_framework, testing, database_orm, devops, build_tool
    confidence: float = 1.0
    evidence_files: List[str] = Field(default_factory=list)
    version: Optional[str] = None


class TechDetector:
    """Detects technological components, frameworks, databases, and test tools."""

    # Definition table: name -> {category, manifest_files, keywords}
    TECH_SIGNATURES = {
        # Backend
        "FastAPI": {
            "category": "backend_framework",
            "files": ["requirements.txt", "pyproject.toml", "Pipfile"],
            "keywords": ["fastapi"],
        },
        "Flask": {
            "category": "backend_framework",
            "files": ["requirements.txt", "pyproject.toml", "Pipfile"],
            "keywords": ["flask"],
        },
        "Django": {
            "category": "backend_framework",
            "files": ["requirements.txt", "pyproject.toml", "Pipfile"],
            "keywords": ["django"],
        },
        "Express": {
            "category": "backend_framework",
            "files": ["package.json"],
            "keywords": ['"express"'],
        },
        "NestJS": {
            "category": "backend_framework",
            "files": ["package.json"],
            "keywords": ['"@nestjs/core"'],
        },
        "Spring Boot": {
            "category": "backend_framework",
            "files": ["pom.xml", "build.gradle", "build.gradle.kts"],
            "keywords": ["spring-boot", "org.springframework.boot"],
        },
        "Gin": {
            "category": "backend_framework",
            "files": ["go.mod"],
            "keywords": ["github.com/gin-gonic/gin"],
        },
        # Frontend
        "React": {
            "category": "frontend_framework",
            "files": ["package.json"],
            "keywords": ['"react"'],
        },
        "Next.js": {
            "category": "frontend_framework",
            "files": ["package.json", "next.config.js", "next.config.mjs", "next.config.ts"],
            "keywords": ['"next"'],
        },
        "Vue": {
            "category": "frontend_framework",
            "files": ["package.json"],
            "keywords": ['"vue"'],
        },
        "Svelte": {
            "category": "frontend_framework",
            "files": ["package.json", "svelte.config.js"],
            "keywords": ['"svelte"'],
        },
        # Testing
        "pytest": {
            "category": "testing",
            "files": ["pytest.ini", "pyproject.toml", "requirements.txt", "setup.cfg"],
            "keywords": ["pytest"],
        },
        "Jest": {
            "category": "testing",
            "files": ["package.json", "jest.config.js", "jest.config.ts"],
            "keywords": ['"jest"'],
        },
        "Vitest": {
            "category": "testing",
            "files": ["package.json", "vitest.config.ts", "vitest.config.js"],
            "keywords": ['"vitest"'],
        },
        "Playwright": {
            "category": "testing",
            "files": ["package.json", "playwright.config.ts"],
            "keywords": ['"@playwright/test"'],
        },
        # ORM / DB
        "SQLAlchemy": {
            "category": "database_orm",
            "files": ["requirements.txt", "pyproject.toml"],
            "keywords": ["sqlalchemy"],
        },
        "Prisma": {
            "category": "database_orm",
            "files": ["package.json", "prisma/schema.prisma"],
            "keywords": ['"@prisma/client"', '"prisma"'],
        },
        "TypeORM": {
            "category": "database_orm",
            "files": ["package.json"],
            "keywords": ['"typeorm"'],
        },
        "Alembic": {
            "category": "database_orm",
            "files": ["alembic.ini", "requirements.txt", "pyproject.toml"],
            "keywords": ["alembic"],
        },
        # DevOps / Container
        "Docker": {
            "category": "devops",
            "files": ["Dockerfile", "docker-compose.yml", "docker-compose.yaml", ".dockerignore"],
            "keywords": [],
        },
        "GitHub Actions": {
            "category": "devops",
            "files": [".github/workflows"],
            "keywords": [],
        },
        "Tailwind CSS": {
            "category": "frontend_styling",
            "files": ["package.json", "tailwind.config.js", "tailwind.config.ts"],
            "keywords": ['"tailwindcss"'],
        },
    }

    ENTRY_POINT_CANDIDATES = [
        "main.py",
        "app.py",
        "server.py",
        "wsgi.py",
        "asgi.py",
        "src/main.py",
        "src/app.py",
        "src/index.ts",
        "src/main.ts",
        "src/server.ts",
        "src/App.tsx",
        "src/index.js",
        "index.js",
        "server.js",
        "main.go",
        "cmd/main.go",
    ]

    def __init__(self, root_path: str):
        self.root_path = Path(root_path).resolve()

    def detect(self) -> List[DetectedTech]:
        """Detect all technologies present in the workspace."""
        detected: List[DetectedTech] = []

        # Cache file existence and small manifest contents
        file_cache: Dict[str, Optional[str]] = {}

        for tech_name, sig in self.TECH_SIGNATURES.items():
            category = sig["category"]
            target_files = sig["files"]
            keywords = sig["keywords"]

            matched_files: List[str] = []

            for target in target_files:
                target_p = self.root_path / target
                if target_p.is_dir():
                    if target_p.exists() and any(target_p.iterdir()):
                        matched_files.append(target)
                elif target_p.is_file():
                    if not keywords:
                        # Existence of file alone is enough evidence (e.g. Dockerfile)
                        matched_files.append(target)
                    else:
                        # Check file contents for keywords
                        if target not in file_cache:
                            try:
                                file_cache[target] = target_p.read_text(encoding="utf-8", errors="ignore").lower()
                            except Exception:
                                file_cache[target] = None

                        content = file_cache.get(target)
                        if content:
                            for kw in keywords:
                                if kw.lower() in content:
                                    matched_files.append(target)
                                    break

            if matched_files:
                detected.append(
                    DetectedTech(
                        name=tech_name,
                        category=category,
                        confidence=1.0 if len(matched_files) > 1 else 0.85,
                        evidence_files=sorted(list(set(matched_files))),
                    )
                )

        return detected

    def find_entry_points(self) -> List[str]:
        """Identify probable application entry point files."""
        entry_points: List[str] = []
        for candidate in self.ENTRY_POINT_CANDIDATES:
            target = self.root_path / candidate
            if target.is_file():
                entry_points.append(candidate)
        return entry_points
