"""
Deterministic repository and file discovery for the Code Graph (Phase 11.2).

The scanner is read-only: it never writes to the repository and never scans
outside the resolved repository root. It produces the Phase 11.1
``GraphBuildResult`` shape with a ``CodeGraph`` containing a repository node
and file nodes, and retains the decoded :class:`SourceFile` records for the
later extraction task.

Discovery policy
----------------
- Only files whose names end in ``.py`` (case-insensitive) are in scope.
- Built-in exclusions cover VCS metadata, virtual environments, caches and
  clearly generated build output. Callers may add directory names or
  repository-relative directory paths via ``exclude_dirs``; built-ins are
  always applied.
- ``.gitignore`` files are honoured with a documented, deterministic subset:
  comments, blank lines, ``!`` negation, anchored leading ``/``,
  directory-only trailing ``/``, ``*``, ``?``, ``**`` and character classes.
  Patterns are case-sensitive on every platform. Root and nested
  ``.gitignore`` files are read; their rules apply relative to the directory
  containing them. Ignored directories are pruned, so a negation cannot
  re-include a file inside a directory that was itself ignored -- the same
  limitation Git has.
- Directory symlinks and Windows directory junctions are never followed. File
  symlinks are followed only when their resolved target stays inside the
  repository root. Escaping links are skipped with a warning diagnostic; they
  are not treated as in-scope.
- ``max_files`` counts supported Python files. If more candidates exist, the
  lexicographically first ``max_files`` are read and truncation is reported.

Line-count rule
---------------
``line_count`` is ``len(decoded_text.splitlines())``. It is 0 for an empty
file, CRLF/CR line endings count once, and a trailing newline does not add an
extra empty line. Hashes and byte sizes always use the raw bytes read from
disk, never the decoded or normalized text.

Status semantics
----------------
- ``complete``: the scan enumerated every in-scope Python file, read and
  decoded all of them, and did not truncate. Warnings (for example skipped
  symlinked directories) do not prevent completion.
- ``partial``: a repository/file graph was assembled, but at least one
  in-scope file was unreadable, failed decoding, or was skipped by the file
  limit. Partial results retain every file that was read.
- ``failed``: the root is missing, is not a directory, cannot be listed, or
  the repository identity configuration is invalid. No graph is returned.

``repository.source_digest`` is computed from the readable files included in
this result. For a partial scan it therefore describes the usable file set,
not unreadable or truncated candidates.
"""

from __future__ import annotations

import hashlib
import io
import os
import re
import stat
import tokenize
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional, Sequence

from app.code_graph.models import (
    CodeGraph,
    DiagnosticSeverity,
    FileNode,
    GraphBuildResult,
    GraphBuildStatus,
    GraphDiagnostic,
    LanguageCoverage,
    RepositoryNode,
    SourceFile,
    canonical_json,
    compute_file_id,
    compute_repository_id,
    sha256_hex,
)
from app.core.path_guard import PathContainmentError, resolve_repository_path


PYTHON_EXTENSION = ".py"
PYTHON_LANGUAGE = "python"
DEFAULT_MAX_FILES = 10_000

DEFAULT_EXCLUDE_DIRS = frozenset(
    {
        ".git",
        ".hg",
        ".svn",
        ".venv",
        "venv",
        "__pycache__",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        ".tox",
        ".nox",
        ".eggs",
        ".cache",
        ".idea",
        ".vscode",
        ".next",
        ".nuxt",
        "node_modules",
        "site-packages",
        "dist",
        "build",
        "coverage",
        "htmlcov",
        "target",
    }
)

_WINDOWS_DRIVE_RE = re.compile(r"^[A-Za-z]:")


# ---------------------------------------------------------------------------
# Diagnostics
# ---------------------------------------------------------------------------


def _diagnostic(
    code: str,
    message: str,
    *,
    severity: DiagnosticSeverity,
    relative_path: Optional[str] = None,
) -> GraphDiagnostic:
    return GraphDiagnostic(
        code=code,
        message=message,
        severity=severity,
        relative_path=relative_path,
    )


def _failed(code: str, message: str) -> GraphBuildResult:
    return GraphBuildResult(
        graph=None,
        status=GraphBuildStatus.FAILED,
        errors=[
            _diagnostic(code, message, severity=DiagnosticSeverity.FATAL),
        ],
    )


def _diagnostic_sort_key(diagnostic: GraphDiagnostic) -> tuple:
    return (
        diagnostic.relative_path or "",
        diagnostic.line or 0,
        diagnostic.code,
        diagnostic.message,
        diagnostic.severity.value,
    )


# ---------------------------------------------------------------------------
# .gitignore subset
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _IgnoreRule:
    """A compiled .gitignore rule, relative to its containing directory."""

    regex: re.Pattern[str]
    negated: bool
    directory_only: bool


@dataclass(frozen=True)
class _IgnoreRuleGroup:
    """Rules from one .gitignore file, applied relative to ``base``."""

    base: str
    rules: tuple[_IgnoreRule, ...]


def _translate_gitignore_pattern(pattern: str) -> str:
    """Translate a single .gitignore glob body to a regular-expression body."""
    output: list[str] = []
    index = 0
    while index < len(pattern):
        character = pattern[index]
        if character == "\\":
            if index + 1 < len(pattern):
                output.append(re.escape(pattern[index + 1]))
                index += 2
                continue
            output.append(re.escape(character))
        elif character == "*":
            if pattern.startswith("**", index):
                index += 2
                if index < len(pattern) and pattern[index] == "/":
                    output.append("(?:[^/]+/)*")
                    index += 1
                else:
                    output.append(".*")
                continue
            output.append("[^/]*")
        elif character == "?":
            output.append("[^/]")
        elif character == "[":
            closing = pattern.find("]", index + 1)
            if closing == -1:
                output.append(r"\[")
            else:
                content = pattern[index + 1 : closing]
                if content.startswith("!"):
                    content = "^" + content[1:]
                output.append("[" + content + "]")
                index = closing
        else:
            output.append(re.escape(character))
        index += 1
    return "".join(output)


def _parse_gitignore(text: str) -> tuple[_IgnoreRule, ...]:
    rules: list[_IgnoreRule] = []
    for raw_line in text.splitlines():
        line = raw_line.rstrip("\r")

        escaped_leading_character = line.startswith(("\\#", "\\!"))
        if escaped_leading_character:
            line = line[1:]
        elif not line.strip() or line.startswith("#"):
            continue

        negated = not escaped_leading_character and line.startswith("!")
        if negated:
            line = line[1:]
        if not line:
            continue

        directory_only = line.endswith("/")
        if directory_only:
            line = line[:-1]
        anchored = line.startswith("/")
        if anchored:
            line = line[1:]
        if not line:
            continue

        body = _translate_gitignore_pattern(line)
        if anchored or "/" in line:
            expression = "^" + body + "$"
        else:
            expression = r"(?:^|.*/)" + body + "$"
        rules.append(
            _IgnoreRule(
                regex=re.compile(expression),
                negated=negated,
                directory_only=directory_only,
            )
        )
    return tuple(rules)


def _is_gitignored(
    relative_path: str,
    is_directory: bool,
    groups: Sequence[_IgnoreRuleGroup],
) -> bool:
    """Evaluate all applicable rules; the last match wins."""
    ignored = False
    for group in groups:
        if group.base:
            prefix = group.base + "/"
            if not relative_path.startswith(prefix):
                continue
            candidate = relative_path[len(prefix) :]
        else:
            candidate = relative_path

        for rule in group.rules:
            if rule.directory_only and not is_directory:
                continue
            if rule.regex.match(candidate):
                ignored = not rule.negated
    return ignored


# ---------------------------------------------------------------------------
# Exclusions and path helpers
# ---------------------------------------------------------------------------


def _normalize_exclude_dirs(extra: Iterable[str] | None) -> frozenset[str]:
    if isinstance(extra, str):
        raise ValueError(
            "exclude_dirs must be an iterable of directory names, not a string."
        )
    excludes = set(DEFAULT_EXCLUDE_DIRS)
    for value in extra or ():
        if not isinstance(value, str):
            raise ValueError("exclude_dirs entries must be strings.")
        normalized = value.strip().replace("\\", "/")
        if not normalized:
            raise ValueError("exclude_dirs entries must not be empty.")
        if normalized.startswith("/") or _WINDOWS_DRIVE_RE.match(normalized):
            raise ValueError(
                "exclude_dirs entries must be directory names or repository-"
                f"relative paths, not absolute paths: '{value}'"
            )
        parts = [part for part in normalized.split("/") if part not in ("", ".")]
        if not parts:
            raise ValueError(f"Invalid exclude_dirs entry: '{value}'")
        if any(part == ".." for part in parts):
            raise ValueError(
                f"exclude_dirs entries must not contain '..': '{value}'"
            )
        excludes.add("/".join(parts))
    return frozenset(excludes)


def _is_python_file(name: str) -> bool:
    return name.lower().endswith(PYTHON_EXTENSION)


def _snapshot_digest(pairs: Sequence[tuple[str, str]]) -> str:
    """SHA-256 of the canonical sorted ``[path, content_hash]`` snapshot."""
    payload = {
        "files": [
            [relative_path, content_hash]
            for relative_path, content_hash in pairs
        ]
    }
    return sha256_hex(canonical_json(payload))


def _is_windows_junction(entry: os.DirEntry) -> bool:
    """Return True for a Windows directory junction (a reparse-point link)."""
    if os.name != "nt":
        return False
    try:
        metadata = entry.stat(follow_symlinks=False)
    except OSError:
        return False
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    mount_tag = getattr(stat, "IO_REPARSE_TAG_MOUNT_POINT", 0)
    return bool(
        getattr(metadata, "st_file_attributes", 0) & reparse_flag
    ) and getattr(metadata, "st_reparse_tag", 0) == mount_tag


def _is_directory_link(entry: os.DirEntry) -> bool:
    """Return True when a directory entry is a symlink or a Windows junction."""
    return entry.is_symlink() or _is_windows_junction(entry)


def _detect_git_origin(root: Path) -> Optional[str]:
    """Return the Git ``origin`` URL of ``root`` itself, if it is a repository."""
    try:
        from configparser import Error as ConfigParserError

        from git import Repo
        from git.exc import GitError
    except ImportError:  # pragma: no cover - GitPython is a declared dependency
        return None

    try:
        repository = Repo(str(root), search_parent_directories=False)
    except (GitError, OSError, ValueError, ConfigParserError):
        return None

    try:
        return repository.remotes.origin.url
    except (AttributeError, IndexError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Internal discovery records
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _Discoverable:
    relative_path: str
    content: str
    content_hash: str
    byte_size: int
    line_count: int


# ---------------------------------------------------------------------------
# Scanner
# ---------------------------------------------------------------------------


class RepositoryScanner:
    """
    Deterministic, read-only repository scanner for Python source files.

    ``scan()`` returns the approved :class:`GraphBuildResult` contract;
    ``discover()`` returns the ordered :class:`SourceFile` records required by
    the extraction phase. Both read the repository exactly once per call.
    """

    def __init__(
        self,
        root_path: str | os.PathLike[str],
        *,
        exclude_dirs: Iterable[str] | None = (),
        max_files: int = DEFAULT_MAX_FILES,
        repository_id: Optional[str] = None,
        origin: Optional[str] = None,
        repository_key: Optional[str] = None,
    ) -> None:
        if (
            not isinstance(max_files, int)
            or isinstance(max_files, bool)
            or max_files < 1
        ):
            raise ValueError("max_files must be a positive integer.")
        self.root_path = root_path
        self.exclude_dirs = _normalize_exclude_dirs(exclude_dirs)
        self.max_files = max_files
        self.repository_id = repository_id
        self.origin = origin
        self.repository_key = repository_key
        self._source_files: list[SourceFile] = []
        self._last_result: Optional[GraphBuildResult] = None

    @property
    def source_files(self) -> list[SourceFile]:
        """Decoded source files from the most recent scan (stable order)."""
        return list(self._source_files)

    @property
    def last_result(self) -> Optional[GraphBuildResult]:
        """Result of the most recent scan, or ``None`` before the first scan."""
        return self._last_result

    # -- public entry points -------------------------------------------------

    def discover(self) -> list[SourceFile]:
        """
        Scan the repository and return its ordered source files.

        An invalid root or identity configuration yields an empty list; inspect
        :attr:`last_result` for the failed status and diagnostics.
        """
        self.scan()
        return self.source_files

    def scan(self) -> GraphBuildResult:
        """Scan the repository and return a complete/partial/failed result."""
        self._source_files = []
        result = self._scan()
        self._last_result = result
        return result

    # -- scan phases ---------------------------------------------------------

    def _scan(self) -> GraphBuildResult:
        root = self._resolve_root()
        if isinstance(root, GraphBuildResult):
            return root

        errors: list[GraphDiagnostic] = []
        warnings: list[GraphDiagnostic] = []
        candidates = self._collect_candidates(root, errors, warnings)
        candidates.sort()

        truncated = len(candidates) > self.max_files
        selected = candidates[: self.max_files]
        if truncated:
            warnings.append(
                _diagnostic(
                    "file_limit_reached",
                    (
                        f"File limit of {self.max_files} reached; "
                        f"{len(candidates) - self.max_files} supported file(s) "
                        "were not read."
                    ),
                    severity=DiagnosticSeverity.WARNING,
                )
            )

        discovered = self._read_selected(root, selected, errors)

        pairs = [
            (record.relative_path, record.content_hash) for record in discovered
        ]
        pairs.sort(key=lambda pair: pair[0])

        effective_origin: Optional[str]
        if self.origin is not None:
            effective_origin = self.origin
        elif self.repository_id is None:
            effective_origin = _detect_git_origin(root)
        else:
            effective_origin = None

        try:
            repository_id = compute_repository_id(
                self.repository_id,
                origin=effective_origin,
                repository_key=self.repository_key,
                files=pairs,
            )
        except ValueError as error:
            return _failed(
                "repository_identity_invalid",
                f"Invalid repository identity configuration: {error}",
            )

        source_digest = _snapshot_digest(pairs)
        try:
            repository = RepositoryNode(
                repository_id=repository_id,
                name=root.name or "repository",
                root_path=str(root),
                source_digest=source_digest,
            )
            file_nodes = [
                FileNode(
                    id=compute_file_id(repository_id, record.relative_path),
                    repository_id=repository_id,
                    relative_path=record.relative_path,
                    language=PYTHON_LANGUAGE,
                    content_hash=record.content_hash,
                    line_count=record.line_count,
                    byte_size=record.byte_size,
                )
                for record in discovered
            ]
            graph = CodeGraph(
                repository=repository,
                files=file_nodes,
                source_digest=source_digest,
            )
        except ValueError as error:
            return _failed(
                "graph_assembly_failed",
                f"Could not assemble repository/file graph: {error}",
            )

        analyzed = len(discovered)
        coverage = [
            LanguageCoverage(
                language=PYTHON_LANGUAGE,
                supported=True,
                discovered_files=len(candidates),
                analyzed_files=analyzed,
                skipped_files=len(candidates) - analyzed,
            )
        ]

        errors.sort(key=_diagnostic_sort_key)
        warnings.sort(key=_diagnostic_sort_key)
        status = (
            GraphBuildStatus.PARTIAL
            if errors or truncated
            else GraphBuildStatus.COMPLETE
        )

        result = GraphBuildResult(
            graph=graph,
            status=status,
            coverage=coverage,
            truncated=truncated,
            errors=errors,
            warnings=warnings,
            file_count=len(file_nodes),
        )
        self._source_files = [
            SourceFile(
                relative_path=record.relative_path,
                language=PYTHON_LANGUAGE,
                content=record.content,
                content_hash=record.content_hash,
                byte_size=record.byte_size,
                line_count=record.line_count,
            )
            for record in discovered
        ]
        return result

    def _resolve_root(self) -> Path | GraphBuildResult:
        if isinstance(self.root_path, str) and not self.root_path.strip():
            return _failed(
                "repository_root_invalid",
                "Repository root must not be empty.",
            )
        try:
            root = Path(self.root_path).expanduser()
        except (TypeError, ValueError, RuntimeError):
            return _failed(
                "repository_root_invalid",
                "Repository root must be a valid filesystem path.",
            )

        try:
            if not root.exists():
                return _failed(
                    "repository_root_missing",
                    "Repository root does not exist.",
                )
            if not root.is_dir():
                return _failed(
                    "repository_root_not_directory",
                    "Repository root must be a directory.",
                )
            resolved = root.resolve(strict=True)
        except OSError:
            return _failed(
                "repository_root_unreadable",
                "Repository root could not be resolved or read.",
            )

        try:
            with os.scandir(resolved) as iterator:
                next(iterator, None)
        except OSError:
            return _failed(
                "repository_root_unreadable",
                "Repository root is not readable.",
            )
        return resolved

    def _collect_candidates(
        self,
        root: Path,
        errors: list[GraphDiagnostic],
        warnings: list[GraphDiagnostic],
    ) -> list[str]:
        candidates: list[str] = []
        stack: list[tuple[Path, str, tuple[_IgnoreRuleGroup, ...]]] = [
            (root, "", ())
        ]

        while stack:
            directory, relative_dir, groups = stack.pop()
            groups = self._load_gitignore(
                root, directory, relative_dir, groups, warnings
            )

            try:
                with os.scandir(directory) as iterator:
                    entries = sorted(iterator, key=lambda entry: entry.name)
            except OSError:
                errors.append(
                    _diagnostic(
                        "directory_unreadable",
                        "Directory could not be listed; its contents were skipped.",
                        severity=DiagnosticSeverity.ERROR,
                        relative_path=relative_dir or None,
                    )
                )
                continue

            for entry in entries:
                relative_path = (
                    f"{relative_dir}/{entry.name}" if relative_dir else entry.name
                )

                if entry.is_dir(follow_symlinks=False):
                    if self._is_excluded(relative_path):
                        continue
                    if _is_gitignored(relative_path, True, groups):
                        continue
                    if _is_directory_link(entry):
                        warnings.append(
                            _diagnostic(
                                "symlinked_directory_skipped",
                                "Linked directory (symlink or junction) was not "
                                "followed.",
                                severity=DiagnosticSeverity.WARNING,
                                relative_path=relative_path,
                            )
                        )
                        continue
                    stack.append((Path(entry.path), relative_path, groups))
                    continue

                if entry.is_symlink() and entry.is_dir(follow_symlinks=True):
                    if self._is_excluded(relative_path):
                        continue
                    if _is_gitignored(relative_path, True, groups):
                        continue
                    warnings.append(
                        _diagnostic(
                            "symlinked_directory_skipped",
                            "Linked directory (symlink or junction) was not "
                            "followed.",
                            severity=DiagnosticSeverity.WARNING,
                            relative_path=relative_path,
                        )
                    )
                    continue

                if not _is_python_file(entry.name):
                    continue
                if _is_gitignored(relative_path, False, groups):
                    continue
                if self._is_excluded(relative_path):
                    continue

                if entry.is_symlink():
                    try:
                        target = resolve_repository_path(root, relative_path)
                    except PathContainmentError:
                        warnings.append(
                            _diagnostic(
                                "symlink_outside_root",
                                "Symlink resolves outside the repository root and "
                                "was skipped.",
                                severity=DiagnosticSeverity.WARNING,
                                relative_path=relative_path,
                            )
                        )
                        continue
                    except OSError:
                        errors.append(
                            _diagnostic(
                                "file_unreadable",
                                "Symlink could not be resolved.",
                                severity=DiagnosticSeverity.ERROR,
                                relative_path=relative_path,
                            )
                        )
                        continue
                    if target.is_dir():
                        warnings.append(
                            _diagnostic(
                                "symlinked_directory_skipped",
                                "Symlinked directory was not followed.",
                                severity=DiagnosticSeverity.WARNING,
                                relative_path=relative_path,
                            )
                        )
                        continue
                    candidates.append(relative_path)
                    continue

                if not entry.is_file(follow_symlinks=False):
                    errors.append(
                        _diagnostic(
                            "file_not_regular",
                            "Supported source path is not a regular file and was "
                            "skipped.",
                            severity=DiagnosticSeverity.ERROR,
                            relative_path=relative_path,
                        )
                    )
                    continue

                try:
                    resolve_repository_path(root, relative_path)
                except PathContainmentError:
                    warnings.append(
                        _diagnostic(
                            "symlink_outside_root",
                            "Path resolves outside the repository root and was "
                            "skipped.",
                            severity=DiagnosticSeverity.WARNING,
                            relative_path=relative_path,
                        )
                    )
                    continue
                except OSError:
                    errors.append(
                        _diagnostic(
                            "file_unreadable",
                            "File path could not be resolved.",
                            severity=DiagnosticSeverity.ERROR,
                            relative_path=relative_path,
                        )
                    )
                    continue

                candidates.append(relative_path)

        return candidates

    def _is_excluded(self, relative_path: str) -> bool:
        name = relative_path.rsplit("/", 1)[-1]
        return name in self.exclude_dirs or relative_path in self.exclude_dirs

    def _load_gitignore(
        self,
        root: Path,
        directory: Path,
        relative_dir: str,
        groups: tuple[_IgnoreRuleGroup, ...],
        warnings: list[GraphDiagnostic],
    ) -> tuple[_IgnoreRuleGroup, ...]:
        ignore_path = directory / ".gitignore"
        try:
            if not ignore_path.is_file():
                return groups
        except OSError:
            return groups

        relative_ignore = (
            f"{relative_dir}/.gitignore" if relative_dir else ".gitignore"
        )

        if ignore_path.is_symlink():
            try:
                resolve_repository_path(root, relative_ignore)
            except PathContainmentError:
                warnings.append(
                    _diagnostic(
                        "symlink_outside_root",
                        "Symlinked .gitignore resolves outside the repository "
                        "root and was skipped.",
                        severity=DiagnosticSeverity.WARNING,
                        relative_path=relative_ignore,
                    )
                )
                return groups
            except OSError:
                warnings.append(
                    _diagnostic(
                        "gitignore_unreadable",
                        ".gitignore could not be resolved and was skipped.",
                        severity=DiagnosticSeverity.WARNING,
                        relative_path=relative_ignore,
                    )
                )
                return groups

        try:
            text = ignore_path.read_bytes().decode("utf-8", errors="replace")
        except OSError:
            warnings.append(
                _diagnostic(
                    "gitignore_unreadable",
                    ".gitignore could not be read and was skipped.",
                    severity=DiagnosticSeverity.WARNING,
                    relative_path=relative_ignore,
                )
            )
            return groups

        rules = _parse_gitignore(text)
        if not rules:
            return groups
        return (*groups, _IgnoreRuleGroup(base=relative_dir, rules=rules))

    def _read_selected(
        self,
        root: Path,
        selected: Sequence[str],
        errors: list[GraphDiagnostic],
    ) -> list[_Discoverable]:
        records: list[_Discoverable] = []
        for relative_path in selected:
            try:
                absolute_path = resolve_repository_path(root, relative_path)
            except (PathContainmentError, OSError):
                errors.append(
                    _diagnostic(
                        "file_unreadable",
                        "File path could not be resolved inside the repository.",
                        severity=DiagnosticSeverity.ERROR,
                        relative_path=relative_path,
                    )
                )
                continue

            try:
                raw = absolute_path.read_bytes()
            except OSError as error:
                errors.append(
                    _diagnostic(
                        "file_unreadable",
                        f"File could not be read ({type(error).__name__}).",
                        severity=DiagnosticSeverity.ERROR,
                        relative_path=relative_path,
                    )
                )
                continue

            try:
                encoding, _ = tokenize.detect_encoding(io.BytesIO(raw).readline)
                content = raw.decode(encoding)
            except (SyntaxError, UnicodeDecodeError, LookupError) as error:
                errors.append(
                    _diagnostic(
                        "file_decode_error",
                        f"File could not be decoded ({type(error).__name__}).",
                        severity=DiagnosticSeverity.ERROR,
                        relative_path=relative_path,
                    )
                )
                continue

            records.append(
                _Discoverable(
                    relative_path=relative_path,
                    content=content,
                    content_hash=hashlib.sha256(raw).hexdigest(),
                    byte_size=len(raw),
                    line_count=len(content.splitlines()),
                )
            )
        return records


__all__ = [
    "DEFAULT_EXCLUDE_DIRS",
    "DEFAULT_MAX_FILES",
    "PYTHON_EXTENSION",
    "PYTHON_LANGUAGE",
    "RepositoryScanner",
]
