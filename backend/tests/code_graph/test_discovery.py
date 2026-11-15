"""Tests for deterministic Code Graph repository/file discovery (Phase 11.2)."""

from __future__ import annotations

import hashlib
import os
import subprocess
from pathlib import Path

import pytest

from app.code_graph import discovery
from app.code_graph.discovery import RepositoryScanner
from app.code_graph.models import (
    DiagnosticSeverity,
    GraphBuildStatus,
    canonical_json,
    compute_repository_id,
    sha256_hex,
)


def _write(root: Path, relative_path: str, content: bytes | str) -> Path:
    path = root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(
        content.encode("utf-8") if isinstance(content, str) else content
    )
    return path


def _paths(result) -> list[str]:
    assert result.graph is not None
    return [file.relative_path for file in result.graph.files]


def _symlink_or_skip(target: Path, link: Path, *, directory: bool = False) -> None:
    try:
        os.symlink(target, link, target_is_directory=directory)
    except (OSError, NotImplementedError) as error:
        pytest.skip(f"Symlinks are not available in this environment: {error}")


# ---------------------------------------------------------------------------
# Root validation and basic discovery
# ---------------------------------------------------------------------------


def test_valid_repository_discovery(tmp_path: Path) -> None:
    _write(tmp_path, "main.py", "print('hello')\n")
    _write(tmp_path, "pkg/__init__.py", "")
    _write(tmp_path, "pkg/module.py", "VALUE = 1\n")

    scanner = RepositoryScanner(tmp_path)
    result = scanner.scan()

    assert result.status == GraphBuildStatus.COMPLETE
    assert result.graph is not None
    assert result.errors == []
    assert result.truncated is False
    assert result.file_count == 3
    assert _paths(result) == ["main.py", "pkg/__init__.py", "pkg/module.py"]

    repository = result.graph.repository
    assert repository.repository_id.startswith(("repo:v1:", "snapshot:v1:"))
    assert repository.id == repository.repository_id
    assert repository.name == tmp_path.name
    assert repository.root_path == str(tmp_path.resolve())
    assert result.graph.source_digest == repository.source_digest

    assert [source.relative_path for source in scanner.source_files] == _paths(result)
    assert all(source.language == "python" for source in scanner.source_files)
    assert all("\\" not in file.relative_path for file in result.graph.files)
    assert all(str(tmp_path.resolve()) not in file.id for file in result.graph.files)

    coverage = result.coverage[0]
    assert coverage.language == "python"
    assert coverage.supported is True
    assert (coverage.discovered_files, coverage.analyzed_files, coverage.skipped_files) == (
        3,
        3,
        0,
    )

    for file in result.graph.files:
        assert file.id.startswith("file:v1:")
        assert len(file.content_hash) == 64
        assert file.byte_size >= 0
        assert file.line_count >= 0


def test_missing_root_fails(tmp_path: Path) -> None:
    result = RepositoryScanner(tmp_path / "does-not-exist").scan()

    assert result.status == GraphBuildStatus.FAILED
    assert result.graph is None
    assert len(result.errors) == 1
    assert result.errors[0].severity == DiagnosticSeverity.FATAL
    assert result.errors[0].code == "repository_root_missing"


def test_file_instead_of_directory_fails(tmp_path: Path) -> None:
    root = tmp_path / "not-a-directory.py"
    root.write_text("x = 1\n", encoding="utf-8")

    result = RepositoryScanner(root).scan()

    assert result.status == GraphBuildStatus.FAILED
    assert result.graph is None
    assert result.errors[0].severity == DiagnosticSeverity.FATAL
    assert result.errors[0].code == "repository_root_not_directory"


def test_empty_root_fails() -> None:
    result = RepositoryScanner("").scan()

    assert result.status == GraphBuildStatus.FAILED
    assert result.graph is None
    assert result.errors[0].code == "repository_root_invalid"


def test_unreadable_root_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _write(tmp_path, "main.py", "x = 1\n")
    real_scandir = os.scandir

    def denied_scandir(path):
        if Path(path) == tmp_path.resolve():
            raise PermissionError("denied")
        return real_scandir(path)

    monkeypatch.setattr(os, "scandir", denied_scandir)

    result = RepositoryScanner(tmp_path).scan()

    assert result.status == GraphBuildStatus.FAILED
    assert result.graph is None
    assert result.errors[0].code == "repository_root_unreadable"
    assert result.errors[0].severity == DiagnosticSeverity.FATAL


def test_empty_repository_is_complete(tmp_path: Path) -> None:
    result = RepositoryScanner(tmp_path).scan()

    assert result.status == GraphBuildStatus.COMPLETE
    assert result.graph is not None
    assert result.graph.files == []
    assert result.graph.symbols == []
    assert result.graph.edges == []
    assert result.file_count == 0
    assert result.truncated is False
    assert result.errors == []
    coverage = result.coverage[0]
    assert (coverage.discovered_files, coverage.analyzed_files, coverage.skipped_files) == (
        0,
        0,
        0,
    )
    assert len(result.graph.repository.source_digest) == 64


def test_nested_files_are_sorted(tmp_path: Path) -> None:
    _write(tmp_path, "z.py", "")
    _write(tmp_path, "a/b.py", "")
    _write(tmp_path, "a/a.py", "")
    _write(tmp_path, "a/deep/nested.py", "")

    result = RepositoryScanner(tmp_path).scan()

    assert _paths(result) == ["a/a.py", "a/b.py", "a/deep/nested.py", "z.py"]


def test_non_python_files_are_excluded(tmp_path: Path) -> None:
    _write(tmp_path, "keep.py", "")
    _write(tmp_path, "upper.PY", "")
    _write(tmp_path, "readme.txt", "")
    _write(tmp_path, "types.pyi", "")
    _write(tmp_path, "script.py.bak", "")

    result = RepositoryScanner(tmp_path).scan()

    assert _paths(result) == ["keep.py", "upper.PY"]
    assert result.status == GraphBuildStatus.COMPLETE


# ---------------------------------------------------------------------------
# Exclusion policy
# ---------------------------------------------------------------------------


def test_vcs_environment_and_generated_directories_are_excluded(
    tmp_path: Path,
) -> None:
    excluded = [
        ".git",
        ".hg",
        ".svn",
        ".venv",
        "venv",
        "__pycache__",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        "node_modules",
        "dist",
        "build",
        "coverage",
        "site-packages",
    ]
    for directory in excluded:
        _write(tmp_path, f"{directory}/hidden.py", "raise SystemExit\n")
    _write(tmp_path, "main.py", "")
    _write(tmp_path, ".github/scripts/visible.py", "")

    result = RepositoryScanner(tmp_path).scan()

    assert _paths(result) == [".github/scripts/visible.py", "main.py"]


def test_gitignore_rules_and_negation(tmp_path: Path) -> None:
    _write(
        tmp_path,
        ".gitignore",
        "\n".join(
            [
                "# comment",
                "",
                "ignored.py",
                "generated/",
                "nested/*.py",
                "!nested/keep.py",
                "/only_root.py",
            ]
        )
        + "\n",
    )
    for relative_path in [
        "ignored.py",
        "keep.py",
        "generated/inside.py",
        "nested/drop.py",
        "nested/keep.py",
        "only_root.py",
        "sub/only_root.py",
        "sub/ok.py",
    ]:
        _write(tmp_path, relative_path, "")

    result = RepositoryScanner(tmp_path).scan()

    assert _paths(result) == [
        "keep.py",
        "nested/keep.py",
        "sub/ok.py",
        "sub/only_root.py",
    ]
    assert result.status == GraphBuildStatus.COMPLETE
    assert result.truncated is False


def test_gitignore_escaped_comment_and_negation_are_literal(tmp_path: Path) -> None:
    _write(tmp_path, ".gitignore", "\\!important.py\n\\#hash.py\n")
    _write(tmp_path, "!important.py", "")
    _write(tmp_path, "#hash.py", "")
    _write(tmp_path, "important.py", "")
    _write(tmp_path, "keep.py", "")

    result = RepositoryScanner(tmp_path).scan()

    # The escaped entries ignore literal filenames; they are not a negation
    # that would re-include ``important.py``.
    assert _paths(result) == ["important.py", "keep.py"]


def test_nested_gitignore_applies_relative_to_its_directory(tmp_path: Path) -> None:
    _write(tmp_path, "pkg/.gitignore", "local.py\ngenerated/\n")
    for relative_path in [
        "pkg/local.py",
        "pkg/generated/inside.py",
        "pkg/ok.py",
        "other/generated/inside.py",
    ]:
        _write(tmp_path, relative_path, "")

    result = RepositoryScanner(tmp_path).scan()

    assert _paths(result) == ["other/generated/inside.py", "pkg/ok.py"]


def test_explicit_exclusions_are_added_to_builtins(tmp_path: Path) -> None:
    _write(tmp_path, "keep.py", "")
    _write(tmp_path, "custom_skip/inside.py", "")
    _write(tmp_path, "pkg/generated/inside.py", "")
    _write(tmp_path, "pkg/keep.py", "")

    result = RepositoryScanner(
        tmp_path,
        exclude_dirs={"custom_skip", "pkg/generated"},
    ).scan()

    assert _paths(result) == ["keep.py", "pkg/keep.py"]


@pytest.mark.parametrize("exclude", ["../escape", "/absolute", "C:/absolute", ""])
def test_invalid_exclusions_are_rejected(tmp_path: Path, exclude: str) -> None:
    with pytest.raises(ValueError):
        RepositoryScanner(tmp_path, exclude_dirs={exclude})


def test_exclude_dirs_must_be_an_iterable_not_a_string(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        RepositoryScanner(tmp_path, exclude_dirs="build")


@pytest.mark.parametrize("max_files", [0, -1, True, 1.5])
def test_invalid_max_files_is_rejected(tmp_path: Path, max_files) -> None:
    with pytest.raises(ValueError):
        RepositoryScanner(tmp_path, max_files=max_files)


# ---------------------------------------------------------------------------
# Determinism and metadata
# ---------------------------------------------------------------------------


def test_output_is_deterministic_across_scans(tmp_path: Path) -> None:
    _write(tmp_path, "b.py", "print('b')\n")
    _write(tmp_path, "a.py", "print('a')\n")
    _write(tmp_path, "c.py", "print('c')\n")

    first_scanner = RepositoryScanner(tmp_path, max_files=2)
    first = first_scanner.scan()
    first_sources = first_scanner.source_files

    second_scanner = RepositoryScanner(tmp_path, max_files=2)
    second = second_scanner.scan()
    second_sources = second_scanner.source_files

    assert first.model_dump() == second.model_dump()
    assert [source.model_dump() for source in first_sources] == [
        source.model_dump() for source in second_sources
    ]
    assert _paths(first) == _paths(second) == ["a.py", "b.py"]
    assert first.truncated is True
    assert second.truncated is True
    assert first.warnings[0].code == "file_limit_reached"


def test_raw_byte_hash_size_and_line_count(tmp_path: Path) -> None:
    fixtures = {
        "empty.py": b"",
        "one_line.py": b"x = 1\n",
        "no_trailing_newline.py": b"a\nb",
        "crlf.py": b"a\r\nb\r\n",
        "unicode.py": "héllo\n".encode("utf-8"),
    }
    for relative_path, content in fixtures.items():
        _write(tmp_path, relative_path, content)

    result = RepositoryScanner(tmp_path).scan()
    by_path = {file.relative_path: file for file in result.graph.files}

    for relative_path, raw in fixtures.items():
        file = by_path[relative_path]
        assert file.content_hash == hashlib.sha256(raw).hexdigest()
        assert file.byte_size == len(raw)

    assert by_path["empty.py"].line_count == 0
    assert by_path["one_line.py"].line_count == 1
    assert by_path["no_trailing_newline.py"].line_count == 2
    assert by_path["crlf.py"].line_count == 2
    assert by_path["unicode.py"].line_count == 1


def test_source_digest_and_snapshot_identity_use_file_hashes(tmp_path: Path) -> None:
    _write(tmp_path, "a.py", "A = 1\n")
    _write(tmp_path, "pkg/b.py", "B = 2\n")

    scanner = RepositoryScanner(tmp_path)
    result = scanner.scan()
    assert result.graph is not None

    pairs = sorted(
        [[file.relative_path, file.content_hash] for file in result.graph.files]
    )
    expected_digest = sha256_hex(canonical_json({"files": pairs}))

    assert result.graph.repository.source_digest == expected_digest
    assert result.graph.repository.repository_id == (
        compute_repository_id(files=[tuple(pair) for pair in pairs])
    )
    assert result.graph.repository.repository_id == f"snapshot:v1:{expected_digest}"


# ---------------------------------------------------------------------------
# Read failures and truncation
# ---------------------------------------------------------------------------


def test_unreadable_file_retains_usable_results(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write(tmp_path, "ok.py", "OK = 1\n")
    _write(tmp_path, "locked.py", "LOCKED = 1\n")

    original_read_bytes = Path.read_bytes

    def read_bytes(self: Path) -> bytes:
        if self.name == "locked.py":
            raise PermissionError("denied")
        return original_read_bytes(self)

    monkeypatch.setattr(Path, "read_bytes", read_bytes)

    scanner = RepositoryScanner(tmp_path)
    result = scanner.scan()

    assert result.status == GraphBuildStatus.PARTIAL
    assert result.truncated is False
    assert _paths(result) == ["ok.py"]
    assert [source.relative_path for source in scanner.source_files] == ["ok.py"]
    assert len(result.errors) == 1
    assert result.errors[0].code == "file_unreadable"
    assert result.errors[0].relative_path == "locked.py"
    assert result.errors[0].severity == DiagnosticSeverity.ERROR
    coverage = result.coverage[0]
    assert (coverage.discovered_files, coverage.analyzed_files, coverage.skipped_files) == (
        2,
        1,
        1,
    )


def test_decode_failures_are_reported_and_ordered(tmp_path: Path) -> None:
    _write(tmp_path, "good.py", "GOOD = 1\n")
    _write(tmp_path, "z_bad.py", b"# coding: utf-8\n\xff\n")
    _write(tmp_path, "a_bad.py", b"# coding: no-such-codec\nX = 1\n")

    result = RepositoryScanner(tmp_path).scan()

    assert result.status == GraphBuildStatus.PARTIAL
    assert _paths(result) == ["good.py"]
    assert [error.code for error in result.errors] == [
        "file_decode_error",
        "file_decode_error",
    ]
    assert [error.relative_path for error in result.errors] == [
        "a_bad.py",
        "z_bad.py",
    ]


@pytest.mark.skipif(
    not hasattr(os, "mkfifo"), reason="Named pipes are not available on this platform"
)
def test_non_regular_python_path_marks_partial(tmp_path: Path) -> None:
    os.mkfifo(tmp_path / "pipe.py")
    _write(tmp_path, "ok.py", "")

    result = RepositoryScanner(tmp_path).scan()

    assert result.status == GraphBuildStatus.PARTIAL
    assert _paths(result) == ["ok.py"]
    assert [error.code for error in result.errors] == ["file_not_regular"]
    assert result.errors[0].relative_path == "pipe.py"


def test_max_file_limit_marks_partial_and_truncated(tmp_path: Path) -> None:
    for name in ["a.py", "b.py", "c.py"]:
        _write(tmp_path, name, f"{name!r}\n")

    result = RepositoryScanner(tmp_path, max_files=2).scan()

    assert result.status == GraphBuildStatus.PARTIAL
    assert result.truncated is True
    assert _paths(result) == ["a.py", "b.py"]
    assert result.errors == []
    assert [warning.code for warning in result.warnings] == ["file_limit_reached"]
    coverage = result.coverage[0]
    assert (coverage.discovered_files, coverage.analyzed_files, coverage.skipped_files) == (
        3,
        2,
        1,
    )


def test_exact_file_limit_is_complete(tmp_path: Path) -> None:
    _write(tmp_path, "a.py", "")
    _write(tmp_path, "b.py", "")

    result = RepositoryScanner(tmp_path, max_files=2).scan()

    assert result.status == GraphBuildStatus.COMPLETE
    assert result.truncated is False
    assert result.warnings == []
    assert _paths(result) == ["a.py", "b.py"]


# ---------------------------------------------------------------------------
# Symlink behaviour and containment
# ---------------------------------------------------------------------------


def test_symlink_outside_root_is_skipped(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    _write(root, "real.py", "REAL = 1\n")
    outside = tmp_path / "outside.py"
    outside.write_text("OUTSIDE = 1\n", encoding="utf-8")
    _symlink_or_skip(outside, root / "escape.py")

    result = RepositoryScanner(root).scan()

    assert _paths(result) == ["real.py"]
    assert result.status == GraphBuildStatus.COMPLETE
    assert [warning.code for warning in result.warnings] == ["symlink_outside_root"]
    assert result.warnings[0].relative_path == "escape.py"


def test_symlink_inside_root_is_included(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    _write(root, "real.py", "REAL = 1\n")
    _symlink_or_skip(root / "real.py", root / "alias.py")

    result = RepositoryScanner(root).scan()

    assert _paths(result) == ["alias.py", "real.py"]
    assert result.status == GraphBuildStatus.COMPLETE
    content_hashes = {file.relative_path: file.content_hash for file in result.graph.files}
    assert content_hashes["alias.py"] == content_hashes["real.py"]


def test_symlinked_directories_are_not_followed(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    _write(root, "real_dir/inside.py", "")
    _symlink_or_skip(root / "real_dir", root / "linked_dir", directory=True)

    outside_dir = tmp_path / "outside_dir"
    outside_dir.mkdir()
    (outside_dir / "outside.py").write_text("OUTSIDE = 1\n", encoding="utf-8")
    _symlink_or_skip(outside_dir, root / "outside_link", directory=True)

    result = RepositoryScanner(root).scan()

    assert _paths(result) == ["real_dir/inside.py"]
    codes = [warning.code for warning in result.warnings]
    assert codes.count("symlinked_directory_skipped") == 2
    assert {warning.relative_path for warning in result.warnings} == {
        "linked_dir",
        "outside_link",
    }
    assert result.status == GraphBuildStatus.COMPLETE


# ---------------------------------------------------------------------------
# Repository identity precedence
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    os.name != "nt", reason="Windows directory junctions are Windows-specific"
)
def test_windows_junction_outside_root_is_not_followed(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "outside.py").write_text("OUTSIDE = 1\n", encoding="utf-8")

    created = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(root / "junction"), str(outside)],
        capture_output=True,
        text=True,
    )
    if created.returncode != 0:
        pytest.skip(f"Could not create a directory junction: {created.stderr}")

    result = RepositoryScanner(root).scan()

    assert _paths(result) == []
    assert result.status == GraphBuildStatus.COMPLETE
    assert [warning.code for warning in result.warnings] == [
        "symlinked_directory_skipped"
    ]
    assert result.warnings[0].relative_path == "junction"


def test_repository_identity_precedence(tmp_path: Path) -> None:
    _write(tmp_path, "a.py", "A = 1\n")
    origin = "git@github.com:Owner/Repo.git"

    explicit = RepositoryScanner(
        tmp_path,
        repository_id="explicit-repository",
        origin=origin,
        repository_key="Owner/Repo",
    ).scan()
    assert explicit.graph is not None
    assert explicit.graph.repository.repository_id == "explicit-repository"

    by_origin = RepositoryScanner(
        tmp_path,
        origin=origin,
        repository_key="Owner/Repo",
    ).scan()
    assert by_origin.graph is not None
    assert by_origin.graph.repository.repository_id == compute_repository_id(
        origin=origin
    )

    by_key = RepositoryScanner(tmp_path, repository_key="Owner/Repo").scan()
    assert by_key.graph is not None
    assert by_key.graph.repository.repository_id == compute_repository_id(
        repository_key="Owner/Repo"
    )

    snapshot = RepositoryScanner(tmp_path).scan()
    assert snapshot.graph is not None
    assert snapshot.graph.repository.repository_id.startswith("snapshot:v1:")


def test_snapshot_identity_changes_with_content(tmp_path: Path) -> None:
    _write(tmp_path, "a.py", "A = 1\n")
    first = RepositoryScanner(tmp_path).scan()
    second = RepositoryScanner(tmp_path).scan()
    assert first.graph is not None and second.graph is not None
    assert (
        first.graph.repository.repository_id
        == second.graph.repository.repository_id
    )

    _write(tmp_path, "a.py", "A = 2\n")
    changed = RepositoryScanner(tmp_path).scan()
    assert changed.graph is not None
    assert (
        changed.graph.repository.repository_id
        != first.graph.repository.repository_id
    )


def test_git_origin_is_detected_when_not_supplied(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write(tmp_path, "a.py", "")
    origin = "ssh://git@github.com/Owner/Repo.git"
    monkeypatch.setattr(discovery, "_detect_git_origin", lambda root: origin)

    result = RepositoryScanner(tmp_path).scan()

    assert result.graph is not None
    assert result.graph.repository.repository_id == compute_repository_id(
        origin=origin
    )


def test_explicit_identity_skips_git_origin_detection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write(tmp_path, "a.py", "")

    def unexpected_detection(root):
        raise AssertionError("Git origin must not be consulted for an explicit ID")

    monkeypatch.setattr(discovery, "_detect_git_origin", unexpected_detection)

    result = RepositoryScanner(
        tmp_path, repository_id="explicit-repository"
    ).scan()

    assert result.graph is not None
    assert result.graph.repository.repository_id == "explicit-repository"


@pytest.mark.parametrize(
    "kwargs",
    [
        {"repository_id": "../escape"},
        {"origin": "file:///tmp/local-repo"},
        {"repository_key": "/absolute/key"},
    ],
)
def test_invalid_identity_configuration_fails(
    tmp_path: Path, kwargs: dict
) -> None:
    _write(tmp_path, "a.py", "")

    result = RepositoryScanner(tmp_path, **kwargs).scan()

    assert result.status == GraphBuildStatus.FAILED
    assert result.graph is None
    assert result.errors[0].code == "repository_identity_invalid"
    assert result.errors[0].severity == DiagnosticSeverity.FATAL


# ---------------------------------------------------------------------------
# Public interface details
# ---------------------------------------------------------------------------


def test_discover_returns_sources_and_records_last_result(tmp_path: Path) -> None:
    _write(tmp_path, "a.py", "A = 1\n")

    scanner = RepositoryScanner(tmp_path)
    assert scanner.last_result is None

    sources = scanner.discover()

    assert [source.relative_path for source in sources] == ["a.py"]
    assert scanner.last_result is not None
    assert scanner.last_result.status == GraphBuildStatus.COMPLETE
    assert [source.relative_path for source in scanner.source_files] == ["a.py"]

    repeated = scanner.discover()
    assert [source.model_dump() for source in repeated] == [
        source.model_dump() for source in sources
    ]


def test_posix_paths_and_case_are_preserved_across_root_forms(
    tmp_path: Path,
) -> None:
    _write(tmp_path, "MixedCase.PY", "VALUE = 1\n")
    _write(tmp_path, "Pkg/Inner.py", "")

    from_path = RepositoryScanner(tmp_path).scan()
    from_string = RepositoryScanner(str(tmp_path)).scan()

    assert _paths(from_path) == ["MixedCase.PY", "Pkg/Inner.py"]
    assert _paths(from_string) == ["MixedCase.PY", "Pkg/Inner.py"]
    assert all("\\" not in path for path in _paths(from_path))
    assert from_path.model_dump() == from_string.model_dump()
