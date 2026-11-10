"""
Phase 6 — Fixture repositories for evaluation.
"""
from pathlib import Path

def create_secure_repo(path: Path):
    path.mkdir(parents=True, exist_ok=True)
    (path / "auth.py").write_text('password = "hardcoded_secret_123"\n')

def create_clean_repo(path: Path):
    path.mkdir(parents=True, exist_ok=True)
    (path / "main.py").write_text("def main():\n    pass\n")

def create_quality_repo(path: Path):
    path.mkdir(parents=True, exist_ok=True)
    (path / "tasks.py").write_text("# TODO fix this later\n")

def create_architecture_repo(path: Path):
    path.mkdir(parents=True, exist_ok=True)
    (path / "deep.py").write_text("def f():\n        if True:\n            if True:\n                if True:\n                    if True:\n                        pass\n")

def create_mixed_repo(path: Path):
    path.mkdir(parents=True, exist_ok=True)
    (path / "mixed.py").write_text('token = "abc"\n# TODO clean\n')

def create_near_miss_repo(path: Path):
    path.mkdir(parents=True, exist_ok=True)
    (path / "near.py").write_text('secret_note = "this is a secret"  # informational only, not a real secret\n')
