"""
Code Graph data models for KiteHut Phase 11.1.

This module defines the canonical, in-memory contract for the Code Graph MVP.
It contains only data models, enums, canonicalization and deterministic
identity helpers. Discovery, AST extraction, relationship resolution, graph
traversal and serialization live in later tasks.

Identity rules (Phase 11 plan, Section 5)
-----------------------------------------
- Repository identity precedence: explicit ``repository_id`` > normalized Git
  ``origin`` > caller-supplied stable key > snapshot of file hashes.
- File IDs: ``file:v1:`` + SHA-256 of canonical JSON
  ``{"repository_id", "relative_path"}``.
- Symbol IDs: ``symbol:v1:`` + SHA-256 of canonical JSON
  ``{"repository_id", "relative_path", "qualified_name", "kind",
  "occurrence_ordinal"}``.
- Edge IDs: ``edge:v1:`` + SHA-256 of canonical JSON containing the repository
  ID, edge kind, source ID, target ID and a provenance discriminator
  (statement file/line/column for IMPORTS and CALLS; the kind and endpoint
  pair for structural CONTAINS/DEFINES edges).
- Canonical JSON is UTF-8, NFC-normalized, sorted-key, compact, and never
  contains absolute machine paths.
"""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from enum import Enum
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


CODE_GRAPH_SCHEMA_VERSION = 1
IDENTITY_VERSION = "v1"

_WINDOWS_DRIVE_RE = re.compile(r"^[A-Za-z]:")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_FILE_ID_RE = re.compile(r"^file:v1:[0-9a-f]{64}$")
_SYMBOL_ID_RE = re.compile(r"^symbol:v1:[0-9a-f]{64}$")
_EDGE_ID_RE = re.compile(r"^edge:v1:[0-9a-f]{64}$")
_SCP_ORIGIN_RE = re.compile(
    r"^(?:[^@/\s:]+@)?(?P<host>[^:/\s]+):(?P<path>[^?#\s]+)$"
)
_DEFAULT_GIT_PORTS = frozenset({22, 80, 443, 9418})


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class NodeKind(str, Enum):
    """Top-level kinds of graph nodes."""

    REPOSITORY = "repository"
    FILE = "file"
    SYMBOL = "symbol"


class SymbolKind(str, Enum):
    """Supported Python declaration kinds."""

    MODULE = "module"
    CLASS = "class"
    FUNCTION = "function"
    ASYNC_FUNCTION = "async_function"
    METHOD = "method"
    ASYNC_METHOD = "async_method"


class EdgeKind(str, Enum):
    """Supported graph relationships."""

    CONTAINS = "contains"
    DEFINES = "defines"
    IMPORTS = "imports"
    CALLS = "calls"


class ResolutionKind(str, Enum):
    """Static resolution state of a relationship or reference."""

    RESOLVED = "resolved"
    UNRESOLVED = "unresolved"
    AMBIGUOUS = "ambiguous"


class EvidenceConfidence(str, Enum):
    """Confidence attached to a source-backed graph fact."""

    EXACT = "exact"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class ProvenanceKind(str, Enum):
    """Edge-type-specific provenance discriminator."""

    DISCOVERED_PATH = "discovered_path"
    DECLARATION = "declaration"
    IMPORT_STATEMENT = "import_statement"
    CALL_SITE = "call_site"


class GraphBuildStatus(str, Enum):
    """Overall outcome of a graph build."""

    COMPLETE = "complete"
    PARTIAL = "partial"
    FAILED = "failed"


class DiagnosticSeverity(str, Enum):
    """Severity of a build or validation diagnostic."""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    FATAL = "fatal"


# ---------------------------------------------------------------------------
# Canonicalization and identity helpers
# ---------------------------------------------------------------------------


def _nfc(value: str) -> str:
    """Return the NFC-normalized form of a string."""
    return unicodedata.normalize("NFC", value)


def _nfc_tree(value: Any) -> Any:
    """Recursively NFC-normalize strings inside JSON-compatible containers."""
    if isinstance(value, str):
        return _nfc(value)
    if isinstance(value, dict):
        return {_nfc(str(key)): _nfc_tree(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_nfc_tree(item) for item in value]
    return value


def canonical_json(value: Any) -> str:
    """
    Serialize a value as canonical UTF-8 JSON.

    Keys are sorted, separators are compact, non-ASCII characters are emitted
    as UTF-8 rather than ``\\u`` escapes, and every string is NFC-normalized.
    """
    return json.dumps(
        _nfc_tree(value),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )


def sha256_hex(value: str) -> str:
    """Return the lowercase SHA-256 hex digest of the UTF-8 bytes of ``value``."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _identity_digest(payload: Any) -> str:
    """Hash canonical JSON identity inputs."""
    return sha256_hex(canonical_json(payload))


def require_sha256(value: str, field_name: str = "hash") -> str:
    """Validate a lowercase 64-character SHA-256 hex digest."""
    if not isinstance(value, str) or not _SHA256_RE.fullmatch(value):
        raise ValueError(
            f"{field_name} must be a lowercase 64-character SHA-256 hex digest."
        )
    return value


def normalize_repository_path(path: str) -> str:
    """
    Normalize a repository-relative path.

    Converts ``\\`` to ``/``, collapses ``.`` and empty segments, NFC-normalizes
    Unicode, preserves case, and rejects absolute paths, drive-letter paths,
    NUL bytes and ``..`` traversal.
    """
    if not isinstance(path, str):
        raise ValueError("Repository-relative paths must be strings.")

    normalized = _nfc(path).replace("\\", "/")
    if not normalized.strip():
        raise ValueError("Repository-relative path must not be empty.")
    if "\x00" in normalized:
        raise ValueError("Repository-relative path must not contain NUL bytes.")
    if normalized.startswith("/") or _WINDOWS_DRIVE_RE.match(normalized):
        raise ValueError(
            f"Absolute paths are not allowed in repository-relative paths: '{path}'"
        )

    segments = [part for part in normalized.split("/") if part not in ("", ".")]
    if not segments:
        raise ValueError(f"Path does not point to a repository entry: '{path}'")
    if any(part == ".." for part in segments):
        raise ValueError(f"Path traversal is not allowed: '{path}'")

    return "/".join(segments)


def _normalize_repository_id(value: str) -> str:
    """Validate an opaque, portable repository identity."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError("repository_id must be a non-empty string.")
    normalized = _nfc(value.strip())
    if "/" in normalized or "\\" in normalized:
        raise ValueError("repository_id must not contain filesystem paths.")
    if any(character.isspace() for character in normalized):
        raise ValueError("repository_id must not contain whitespace.")
    return normalized


def _normalize_reference_id(value: str, field_name: str) -> str:
    """Validate an opaque node reference ID (canonical form is checked by kind)."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty node ID.")
    normalized = _nfc(value.strip())
    if "/" in normalized or "\\" in normalized:
        raise ValueError(f"{field_name} must not contain filesystem paths.")
    if any(character.isspace() for character in normalized):
        raise ValueError(f"{field_name} must not contain whitespace.")
    return normalized


def normalize_origin(origin: str) -> str:
    """
    Normalize a Git ``origin`` URL to ``https://host/owner/repository`` form.

    HTTP(S), ``ssh://``, ``git://`` and SCP-style forms are accepted. Scheme is
    forced to ``https``; credentials, query strings and fragments are stripped;
    the host is lowercased; default ports and a trailing ``.git`` are removed;
    owner/repository path case is preserved.
    """
    if not isinstance(origin, str):
        raise ValueError("Git origin must be a string.")

    raw = _nfc(origin.strip())
    if not raw:
        raise ValueError("Git origin must not be empty.")
    if _WINDOWS_DRIVE_RE.match(raw):
        raise ValueError("Local absolute paths cannot be used as a Git origin.")

    if "://" in raw:
        parsed = urlsplit(raw)
        scheme = parsed.scheme.lower()
        if scheme not in {"http", "https", "ssh", "git"}:
            raise ValueError(f"Unsupported Git origin scheme: '{parsed.scheme}'")
        host = parsed.hostname
        if not host:
            raise ValueError(f"Git origin has no host: '{origin}'")
        host = host.lower()
        try:
            port = parsed.port
        except ValueError as error:
            raise ValueError(f"Git origin has an invalid port: '{origin}'") from error
        path = parsed.path
    else:
        match = _SCP_ORIGIN_RE.match(raw)
        if not match:
            raise ValueError(f"Unsupported Git origin form: '{origin}'")
        host = match.group("host").lower()
        path = match.group("path")
        port = None

    if "\\" in path:
        raise ValueError(f"Git origin path must use '/': '{origin}'")

    segments = [part for part in path.split("/") if part not in ("", ".")]
    if not segments:
        raise ValueError(f"Git origin has no repository path: '{origin}'")
    if any(part == ".." for part in segments):
        raise ValueError(f"Git origin path must not contain '..': '{origin}'")

    if segments[-1].endswith(".git"):
        segments[-1] = segments[-1][: -len(".git")]
    if not segments[-1]:
        raise ValueError(f"Git origin has no repository name: '{origin}'")

    normalized_host = host
    if ":" in normalized_host and not normalized_host.startswith("["):
        normalized_host = f"[{normalized_host}]"
    if port is not None and port not in _DEFAULT_GIT_PORTS:
        normalized_host = f"{normalized_host}:{port}"

    return f"https://{normalized_host}/{_nfc('/'.join(segments))}"


def compute_repository_id(
    explicit_repository_id: Optional[str] = None,
    *,
    origin: Optional[str] = None,
    repository_key: Optional[str] = None,
    files: Optional[Iterable[Tuple[str, str]]] = None,
) -> str:
    """
    Compute a stable repository identity using the Phase 11 precedence.

    Precedence: explicit ID, then Git ``origin``, then a caller-supplied stable
    key, then a snapshot-scoped identity over file hashes. The snapshot fallback
    is intentionally not stable across file changes.
    """
    if explicit_repository_id is not None:
        return _normalize_repository_id(explicit_repository_id)

    if origin is not None:
        return f"repo:{IDENTITY_VERSION}:" + _identity_digest(
            {"origin": normalize_origin(origin)}
        )

    if repository_key is not None:
        key = _nfc(repository_key.strip())
        if not key:
            raise ValueError("repository_key must not be empty.")
        if key.startswith(("/", "\\")) or _WINDOWS_DRIVE_RE.match(key):
            raise ValueError(
                "repository_key must be a stable key, not an absolute filesystem path."
            )
        if "\x00" in key:
            raise ValueError("repository_key must not contain NUL bytes.")
        if any(part == ".." for part in key.replace("\\", "/").split("/")):
            raise ValueError("repository_key must not contain '..' traversal.")
        return f"repo:{IDENTITY_VERSION}:" + _identity_digest({"key": key})

    if files is not None:
        pairs: List[List[str]] = []
        seen_paths: set[str] = set()
        for relative_path, content_hash in files:
            normalized_path = normalize_repository_path(relative_path)
            if normalized_path in seen_paths:
                raise ValueError(
                    f"Duplicate repository path in snapshot identity: '{normalized_path}'"
                )
            seen_paths.add(normalized_path)
            pairs.append([normalized_path, require_sha256(content_hash, "content_hash")])
        pairs.sort(key=lambda pair: pair[0])
        return f"snapshot:{IDENTITY_VERSION}:" + _identity_digest({"files": pairs})

    raise ValueError(
        "A repository identity requires an explicit repository_id, Git origin, "
        "repository_key, or file snapshot."
    )


def compute_file_id(repository_id: str, relative_path: str) -> str:
    """Compute the deterministic versioned ID for a file node."""
    return f"file:{IDENTITY_VERSION}:" + _identity_digest(
        {
            "repository_id": _normalize_repository_id(repository_id),
            "relative_path": normalize_repository_path(relative_path),
        }
    )


def compute_symbol_id(
    repository_id: str,
    relative_path: str,
    qualified_name: str,
    kind: SymbolKind | str,
    occurrence_ordinal: int = 0,
) -> str:
    """Compute the deterministic versioned ID for a symbol node."""
    if not isinstance(qualified_name, str) or not qualified_name.strip():
        raise ValueError("qualified_name must be a non-empty string.")
    if not isinstance(occurrence_ordinal, int) or occurrence_ordinal < 0:
        raise ValueError("occurrence_ordinal must be a non-negative integer.")
    symbol_kind = kind if isinstance(kind, SymbolKind) else SymbolKind(kind)

    return f"symbol:{IDENTITY_VERSION}:" + _identity_digest(
        {
            "repository_id": _normalize_repository_id(repository_id),
            "relative_path": normalize_repository_path(relative_path),
            "qualified_name": _nfc(qualified_name),
            "kind": symbol_kind.value,
            "occurrence_ordinal": occurrence_ordinal,
        }
    )


def compute_edge_id(
    repository_id: str,
    kind: EdgeKind | str,
    source_id: str,
    target_id: str,
    *,
    statement_span: Optional[Tuple[str, int, int, int, int]] = None,
) -> str:
    """
    Compute the deterministic versioned ID for an edge.

    ``statement_span`` is ``(relative_path, start_line, start_column,
    end_line, end_column)`` for statement-backed ``IMPORTS``/``CALLS`` edges.
    Structural ``CONTAINS``/``DEFINES`` edges use the relationship kind and
    endpoint pair as their discriminator.
    """
    edge_kind = kind if isinstance(kind, EdgeKind) else EdgeKind(kind)
    source = _normalize_reference_id(source_id, "source_id")
    target = _normalize_reference_id(target_id, "target_id")

    if statement_span is not None:
        path, start_line, start_column, end_line, end_column = statement_span
        provenance: Dict[str, Any] = {
            "source_file": normalize_repository_path(path),
            "start_line": int(start_line),
            "start_column": int(start_column),
            "end_line": int(end_line),
            "end_column": int(end_column),
        }
    else:
        provenance = {
            "kind": edge_kind.value,
            "source_id": source,
            "target_id": target,
        }

    return f"edge:{IDENTITY_VERSION}:" + _identity_digest(
        {
            "repository_id": _normalize_repository_id(repository_id),
            "kind": edge_kind.value,
            "source_id": source,
            "target_id": target,
            "provenance": provenance,
        }
    )


def validate_source_span(
    start_line: Optional[int],
    end_line: Optional[int],
    start_column: Optional[int] = None,
    end_column: Optional[int] = None,
    *,
    require_columns: bool = False,
    required: bool = True,
) -> None:
    """
    Validate a 1-based inclusive source span.

    Raises ``ValueError`` for missing required coordinates, non-positive
    values, reversed ranges, or a same-line end column before the start column.
    """
    if start_line is None and end_line is None:
        if required:
            raise ValueError("A source span requires start_line and end_line.")
        if start_column is not None or end_column is not None:
            raise ValueError("Source columns require start_line and end_line.")
        return

    if start_line is None or end_line is None:
        raise ValueError("A source span requires both start_line and end_line.")
    if start_line < 1 or end_line < 1:
        raise ValueError("Source spans are 1-based; line numbers must be >= 1.")
    if end_line < start_line:
        raise ValueError("Source span end_line must be >= start_line.")

    if (start_column is None) != (end_column is None):
        raise ValueError(
            "A source span must provide both start_column and end_column or neither."
        )
    if require_columns and (start_column is None or end_column is None):
        raise ValueError("This source span requires start_column and end_column.")
    if start_column is not None and end_column is not None:
        if start_column < 1 or end_column < 1:
            raise ValueError("Source columns are 1-based and must be >= 1.")
        if end_line == start_line and end_column < start_column:
            raise ValueError(
                "Source span end_column must be >= start_column on the same line."
            )


def _is_file_id(value: str) -> bool:
    return bool(_FILE_ID_RE.fullmatch(value))


def _is_symbol_id(value: str) -> bool:
    return bool(_SYMBOL_ID_RE.fullmatch(value))


# ---------------------------------------------------------------------------
# Model base
# ---------------------------------------------------------------------------


class _GraphModel(BaseModel):
    """Base configuration for Code Graph contracts."""

    model_config = ConfigDict(extra="forbid")


class GraphDiagnostic(_GraphModel):
    """A structured build or validation diagnostic."""

    code: str
    message: str
    severity: DiagnosticSeverity = DiagnosticSeverity.ERROR
    entity_id: Optional[str] = None
    relative_path: Optional[str] = None
    line: Optional[int] = Field(default=None, ge=1)

    @field_validator("code", "message")
    @classmethod
    def _require_text(cls, value: str) -> str:
        normalized = _nfc(value.strip())
        if not normalized:
            raise ValueError("Diagnostic code and message must not be empty.")
        return normalized

    @field_validator("relative_path")
    @classmethod
    def _normalize_path(cls, value: Optional[str]) -> Optional[str]:
        return normalize_repository_path(value) if value is not None else value

    @field_validator("entity_id")
    @classmethod
    def _normalize_entity_id(cls, value: Optional[str]) -> Optional[str]:
        return _normalize_reference_id(value, "entity_id") if value is not None else value


# ---------------------------------------------------------------------------
# Graph nodes and edges
# ---------------------------------------------------------------------------


class RepositoryNode(_GraphModel):
    """Root node representing one repository snapshot."""

    id: Optional[str] = None
    repository_id: str
    name: str
    root_path: Optional[str] = None
    revision: Optional[str] = None
    source_digest: str

    @field_validator("repository_id")
    @classmethod
    def _validate_repository_id(cls, value: str) -> str:
        return _normalize_repository_id(value)

    @field_validator("name")
    @classmethod
    def _validate_name(cls, value: str) -> str:
        normalized = _nfc(value.strip())
        if not normalized:
            raise ValueError("Repository name must not be empty.")
        return normalized

    @field_validator("source_digest")
    @classmethod
    def _validate_digest(cls, value: str) -> str:
        return require_sha256(value, "source_digest")

    @model_validator(mode="after")
    def _validate_identity(self) -> "RepositoryNode":
        if self.id is None:
            self.id = self.repository_id
        elif _normalize_repository_id(self.id) != self.repository_id:
            raise ValueError(
                "RepositoryNode.id must equal repository_id; the repository ID "
                "is the node identity."
            )
        return self

    @property
    def node_kind(self) -> NodeKind:
        return NodeKind.REPOSITORY


class FileNode(_GraphModel):
    """A discovered repository file."""

    id: Optional[str] = None
    repository_id: str
    relative_path: str
    language: str
    content_hash: str
    line_count: int = Field(ge=0)
    byte_size: int = Field(ge=0)

    @field_validator("repository_id")
    @classmethod
    def _validate_repository_id(cls, value: str) -> str:
        return _normalize_repository_id(value)

    @field_validator("relative_path")
    @classmethod
    def _validate_relative_path(cls, value: str) -> str:
        return normalize_repository_path(value)

    @field_validator("language")
    @classmethod
    def _validate_language(cls, value: str) -> str:
        normalized = _nfc(value.strip())
        if not normalized:
            raise ValueError("File language must not be empty.")
        return normalized

    @field_validator("content_hash")
    @classmethod
    def _validate_content_hash(cls, value: str) -> str:
        return require_sha256(value, "content_hash")

    @model_validator(mode="after")
    def _validate_identity(self) -> "FileNode":
        expected = compute_file_id(self.repository_id, self.relative_path)
        if self.id is None:
            self.id = expected
        elif self.id != expected:
            raise ValueError(
                "FileNode.id does not match its deterministic file identity "
                "(repository_id + normalized relative_path)."
            )
        return self

    @property
    def node_kind(self) -> NodeKind:
        return NodeKind.FILE


class SymbolNode(_GraphModel):
    """A source declaration extracted from a file."""

    id: Optional[str] = None
    repository_id: str
    file_id: str
    relative_path: str
    name: str
    qualified_name: str
    kind: SymbolKind
    parent_id: Optional[str] = None
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)
    start_column: Optional[int] = Field(default=None, ge=1)
    end_column: Optional[int] = Field(default=None, ge=1)
    source_hash: str
    extractor: str = "python_ast"
    occurrence_ordinal: int = Field(default=0, ge=0)

    @field_validator("repository_id")
    @classmethod
    def _validate_repository_id(cls, value: str) -> str:
        return _normalize_repository_id(value)

    @field_validator("file_id")
    @classmethod
    def _validate_file_id(cls, value: str) -> str:
        if not _is_file_id(value):
            raise ValueError("file_id must be a canonical 'file:v1:<sha256>' ID.")
        return value

    @field_validator("relative_path")
    @classmethod
    def _validate_relative_path(cls, value: str) -> str:
        return normalize_repository_path(value)

    @field_validator("name", "qualified_name")
    @classmethod
    def _validate_name(cls, value: str) -> str:
        normalized = _nfc(value.strip())
        if not normalized:
            raise ValueError("Symbol name and qualified_name must not be empty.")
        return normalized

    @field_validator("parent_id")
    @classmethod
    def _validate_parent_id(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        if not _is_symbol_id(value):
            raise ValueError(
                "parent_id must be a canonical 'symbol:v1:<sha256>' ID."
            )
        return value

    @field_validator("source_hash")
    @classmethod
    def _validate_source_hash(cls, value: str) -> str:
        return require_sha256(value, "source_hash")

    @field_validator("extractor")
    @classmethod
    def _validate_extractor(cls, value: str) -> str:
        normalized = _nfc(value.strip())
        if not normalized:
            raise ValueError("Symbol extractor must not be empty.")
        return normalized

    @model_validator(mode="after")
    def _validate_symbol(self) -> "SymbolNode":
        validate_source_span(
            self.start_line,
            self.end_line,
            self.start_column,
            self.end_column,
            required=True,
        )
        expected = compute_symbol_id(
            self.repository_id,
            self.relative_path,
            self.qualified_name,
            self.kind,
            self.occurrence_ordinal,
        )
        if self.id is None:
            self.id = expected
        elif self.id != expected:
            raise ValueError(
                "SymbolNode.id does not match its deterministic symbol identity "
                "(repository, path, qualified name, kind, occurrence ordinal)."
            )
        return self

    @property
    def node_kind(self) -> NodeKind:
        return NodeKind.SYMBOL


class GraphEdge(_GraphModel):
    """A typed, source-provenanced relationship between two graph nodes."""

    id: Optional[str] = None
    repository_id: str
    source_id: str
    target_id: str
    kind: EdgeKind
    provenance_kind: ProvenanceKind
    source_file: Optional[str] = None
    start_line: Optional[int] = Field(default=None, ge=1)
    end_line: Optional[int] = Field(default=None, ge=1)
    start_column: Optional[int] = Field(default=None, ge=1)
    end_column: Optional[int] = Field(default=None, ge=1)
    source_hash: Optional[str] = None
    confidence: EvidenceConfidence = EvidenceConfidence.HIGH
    resolution: ResolutionKind = ResolutionKind.RESOLVED
    extractor: str = "python_ast"
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("repository_id")
    @classmethod
    def _validate_repository_id(cls, value: str) -> str:
        return _normalize_repository_id(value)

    @field_validator("source_id", "target_id")
    @classmethod
    def _validate_endpoint(cls, value: str) -> str:
        return _normalize_reference_id(value, "edge endpoint")

    @field_validator("source_file")
    @classmethod
    def _validate_source_file(cls, value: Optional[str]) -> Optional[str]:
        return normalize_repository_path(value) if value is not None else value

    @field_validator("source_hash")
    @classmethod
    def _validate_source_hash(cls, value: Optional[str]) -> Optional[str]:
        return require_sha256(value, "source_hash") if value is not None else value

    @field_validator("extractor")
    @classmethod
    def _validate_extractor(cls, value: str) -> str:
        normalized = _nfc(value.strip())
        if not normalized:
            raise ValueError("Edge extractor must not be empty.")
        return normalized

    @model_validator(mode="after")
    def _validate_provenance_and_identity(self) -> "GraphEdge":
        is_repository_containment = (
            self.kind == EdgeKind.CONTAINS
            and self.source_id == self.repository_id
        )

        if self.kind == EdgeKind.CONTAINS:
            if is_repository_containment:
                if not _is_file_id(self.target_id):
                    raise ValueError(
                        "Repository CONTAINS edges must target a canonical file ID."
                    )
                expected_provenance = ProvenanceKind.DISCOVERED_PATH
                statement_backed = False
                required_columns = False
            else:
                if not (_is_file_id(self.source_id) or _is_symbol_id(self.source_id)):
                    raise ValueError(
                        "Lexical CONTAINS edges must originate from a file or symbol ID."
                    )
                if not _is_symbol_id(self.target_id):
                    raise ValueError(
                        "Lexical CONTAINS edges must target a canonical symbol ID."
                    )
                expected_provenance = ProvenanceKind.DECLARATION
                statement_backed = False
                required_columns = False
        elif self.kind == EdgeKind.DEFINES:
            if not _is_file_id(self.source_id):
                raise ValueError("DEFINES edges must originate from a canonical file ID.")
            if not _is_symbol_id(self.target_id):
                raise ValueError("DEFINES edges must target a canonical symbol ID.")
            expected_provenance = ProvenanceKind.DECLARATION
            statement_backed = False
            required_columns = False
        elif self.kind == EdgeKind.IMPORTS:
            if not _is_file_id(self.source_id) or not _is_file_id(self.target_id):
                raise ValueError("IMPORTS edges must connect two canonical file IDs.")
            expected_provenance = ProvenanceKind.IMPORT_STATEMENT
            statement_backed = True
            required_columns = True
        else:  # EdgeKind.CALLS
            if not _is_symbol_id(self.source_id) or not _is_symbol_id(self.target_id):
                raise ValueError("CALLS edges must connect two canonical symbol IDs.")
            expected_provenance = ProvenanceKind.CALL_SITE
            statement_backed = True
            required_columns = True

        if self.provenance_kind != expected_provenance:
            raise ValueError(
                f"{self.kind.value.upper()} edges require provenance "
                f"'{expected_provenance.value}', got '{self.provenance_kind.value}'."
            )

        if self.source_file is None:
            raise ValueError(
                f"{self.kind.value.upper()} edges require the source_file "
                "relative path for provenance."
            )
        if self.source_hash is None:
            raise ValueError(
                f"{self.kind.value.upper()} edges require the source file hash "
                "for provenance."
            )

        validate_source_span(
            self.start_line,
            self.end_line,
            self.start_column,
            self.end_column,
            require_columns=required_columns,
            required=statement_backed or not is_repository_containment,
        )

        statement_span = None
        if statement_backed:
            statement_span = (
                self.source_file,
                self.start_line,
                self.start_column,
                self.end_line,
                self.end_column,
            )

        expected_id = compute_edge_id(
            self.repository_id,
            self.kind,
            self.source_id,
            self.target_id,
            statement_span=statement_span,
        )
        if self.id is None:
            self.id = expected_id
        elif self.id != expected_id:
            raise ValueError(
                "GraphEdge.id does not match its deterministic edge identity."
            )
        return self


# ---------------------------------------------------------------------------
# Graph container and build/validation reports
# ---------------------------------------------------------------------------


class CodeGraph(_GraphModel):
    """Canonical in-memory graph for one repository snapshot."""

    schema_version: int = Field(default=CODE_GRAPH_SCHEMA_VERSION, ge=1)
    repository: RepositoryNode
    files: List[FileNode] = Field(default_factory=list)
    symbols: List[SymbolNode] = Field(default_factory=list)
    edges: List[GraphEdge] = Field(default_factory=list)
    source_digest: Optional[str] = None

    @field_validator("source_digest")
    @classmethod
    def _validate_source_digest(cls, value: Optional[str]) -> Optional[str]:
        return require_sha256(value, "source_digest") if value is not None else value

    @model_validator(mode="after")
    def _validate_graph(self) -> "CodeGraph":
        if self.source_digest is None:
            self.source_digest = self.repository.source_digest
        elif self.source_digest != self.repository.source_digest:
            raise ValueError(
                "CodeGraph.source_digest must match repository.source_digest."
            )

        repository_id = self.repository.repository_id
        for collection_name in ("files", "symbols", "edges"):
            for entity in getattr(self, collection_name):
                if entity.repository_id != repository_id:
                    raise ValueError(
                        f"All {collection_name} must use the graph repository_id "
                        f"'{repository_id}'."
                    )

        seen_ids: set[str] = set()
        for entity in [self.repository, *self.files, *self.symbols, *self.edges]:
            if entity.id in seen_ids:
                raise ValueError(f"Duplicate graph entity ID: '{entity.id}'")
            seen_ids.add(entity.id)

        return self


class LanguageCoverage(_GraphModel):
    """Per-language discovery/analysis coverage for a build."""

    language: str
    supported: bool = True
    discovered_files: int = Field(default=0, ge=0)
    analyzed_files: int = Field(default=0, ge=0)
    skipped_files: int = Field(default=0, ge=0)

    @field_validator("language")
    @classmethod
    def _validate_language(cls, value: str) -> str:
        normalized = _nfc(value.strip())
        if not normalized:
            raise ValueError("Coverage language must not be empty.")
        return normalized

    @model_validator(mode="after")
    def _validate_coverage(self) -> "LanguageCoverage":
        if self.analyzed_files > self.discovered_files:
            raise ValueError(
                "analyzed_files cannot exceed discovered_files for a language."
            )
        if self.skipped_files > self.discovered_files:
            raise ValueError(
                "skipped_files cannot exceed discovered_files for a language."
            )
        if not self.supported and self.analyzed_files:
            raise ValueError(
                "Unsupported language coverage cannot report analyzed files."
            )
        return self


class GraphBuildResult(_GraphModel):
    """Outcome of a graph build, including status and diagnostics."""

    graph: Optional[CodeGraph] = None
    status: GraphBuildStatus
    coverage: List[LanguageCoverage] = Field(default_factory=list)
    truncated: bool = False
    errors: List[GraphDiagnostic] = Field(default_factory=list)
    warnings: List[GraphDiagnostic] = Field(default_factory=list)
    unresolved_imports: List[GraphDiagnostic] = Field(default_factory=list)
    unresolved_calls: List[GraphDiagnostic] = Field(default_factory=list)
    file_count: int = Field(default=0, ge=0)
    symbol_count: int = Field(default=0, ge=0)
    edge_count: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def _validate_status_consistency(self) -> "GraphBuildResult":
        for diagnostic in self.errors:
            if diagnostic.severity not in (
                DiagnosticSeverity.ERROR,
                DiagnosticSeverity.FATAL,
            ):
                raise ValueError(
                    "errors must contain only error or fatal diagnostics."
                )
        for diagnostic in [
            *self.warnings,
            *self.unresolved_imports,
            *self.unresolved_calls,
        ]:
            if diagnostic.severity in (
                DiagnosticSeverity.ERROR,
                DiagnosticSeverity.FATAL,
            ):
                raise ValueError(
                    "warnings and unresolved relationship diagnostics must not "
                    "use error or fatal severity."
                )

        if self.graph is not None:
            if self.file_count != len(self.graph.files):
                raise ValueError("file_count does not match the graph file count.")
            if self.symbol_count != len(self.graph.symbols):
                raise ValueError("symbol_count does not match the graph symbol count.")
            if self.edge_count != len(self.graph.edges):
                raise ValueError("edge_count does not match the graph edge count.")

        fatal = [
            diagnostic
            for diagnostic in self.errors
            if diagnostic.severity == DiagnosticSeverity.FATAL
        ]
        coverage_gap = any(
            entry.supported
            and (
                entry.analyzed_files != entry.discovered_files
                or entry.skipped_files != 0
            )
            for entry in self.coverage
        )

        if self.status == GraphBuildStatus.COMPLETE:
            if self.graph is None:
                raise ValueError("A complete build must include a graph.")
            if self.graph.files and not self.coverage:
                raise ValueError(
                    "A complete build must report per-language coverage for a "
                    "non-empty graph."
                )
            if self.truncated:
                raise ValueError("A truncated build cannot be complete.")
            if self.errors:
                raise ValueError("A complete build must not carry errors.")
            if coverage_gap:
                raise ValueError(
                    "A complete build must process every in-scope supported file."
                )
        elif self.status == GraphBuildStatus.PARTIAL:
            if self.graph is None:
                raise ValueError("A partial build must retain a valid graph.")
            if fatal:
                raise ValueError("A partial build must not carry fatal diagnostics.")
            if not (self.errors or self.truncated or coverage_gap):
                raise ValueError(
                    "A partial build requires a processing error, coverage gap, "
                    "or truncation; unresolved relationships alone do not qualify."
                )
        else:  # GraphBuildStatus.FAILED
            if self.graph is not None:
                raise ValueError("A failed build must not include a graph.")
            if not fatal:
                raise ValueError("A failed build requires at least one fatal diagnostic.")

        return self


class GraphValidationResult(_GraphModel):
    """Outcome of validating an assembled graph."""

    valid: bool
    errors: List[GraphDiagnostic] = Field(default_factory=list)
    warnings: List[GraphDiagnostic] = Field(default_factory=list)
    checked_nodes: int = Field(default=0, ge=0)
    checked_edges: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def _validate_result(self) -> "GraphValidationResult":
        for diagnostic in self.errors:
            if diagnostic.severity not in (
                DiagnosticSeverity.ERROR,
                DiagnosticSeverity.FATAL,
            ):
                raise ValueError(
                    "Validation errors must use error or fatal severity."
                )
        for diagnostic in self.warnings:
            if diagnostic.severity in (
                DiagnosticSeverity.ERROR,
                DiagnosticSeverity.FATAL,
            ):
                raise ValueError(
                    "Validation warnings must not use error or fatal severity."
                )
        if self.valid and self.errors:
            raise ValueError("A valid result cannot carry validation errors.")
        if not self.valid and not self.errors:
            raise ValueError("An invalid result requires at least one error.")
        return self


# ---------------------------------------------------------------------------
# Internal source records (extractor-facing, pre-graph)
# ---------------------------------------------------------------------------


class SourceFile(_GraphModel):
    """A discovered, readable source file and its raw-byte digest."""

    relative_path: str
    language: str
    content: str
    content_hash: str
    byte_size: int = Field(ge=0)
    line_count: int = Field(ge=0)

    @field_validator("relative_path")
    @classmethod
    def _validate_relative_path(cls, value: str) -> str:
        return normalize_repository_path(value)

    @field_validator("language")
    @classmethod
    def _validate_language(cls, value: str) -> str:
        normalized = _nfc(value.strip())
        if not normalized:
            raise ValueError("Source file language must not be empty.")
        return normalized

    @field_validator("content_hash")
    @classmethod
    def _validate_content_hash(cls, value: str) -> str:
        return require_sha256(value, "content_hash")


class SymbolDeclaration(_GraphModel):
    """A declaration extracted from a file, before graph-node assembly."""

    relative_path: str
    name: str
    qualified_name: str
    kind: SymbolKind
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)
    start_column: Optional[int] = Field(default=None, ge=1)
    end_column: Optional[int] = Field(default=None, ge=1)
    parent_qualified_name: Optional[str] = None
    occurrence_ordinal: int = Field(default=0, ge=0)

    @field_validator("relative_path")
    @classmethod
    def _validate_relative_path(cls, value: str) -> str:
        return normalize_repository_path(value)

    @field_validator("name", "qualified_name")
    @classmethod
    def _validate_name(cls, value: str) -> str:
        normalized = _nfc(value.strip())
        if not normalized:
            raise ValueError("Declaration name must not be empty.")
        return normalized

    @field_validator("parent_qualified_name")
    @classmethod
    def _validate_parent(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        normalized = _nfc(value.strip())
        if not normalized:
            raise ValueError("parent_qualified_name must not be empty when provided.")
        return normalized

    @model_validator(mode="after")
    def _validate_span(self) -> "SymbolDeclaration":
        validate_source_span(
            self.start_line,
            self.end_line,
            self.start_column,
            self.end_column,
            required=True,
        )
        return self


class ImportReference(_GraphModel):
    """A syntactic import statement with its exact source span."""

    relative_path: str
    module: str = ""
    imported_names: List[str] = Field(default_factory=list)
    alias: Optional[str] = None
    level: int = Field(default=0, ge=0)
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)
    start_column: int = Field(ge=1)
    end_column: int = Field(ge=1)
    source_hash: str

    @field_validator("relative_path")
    @classmethod
    def _validate_relative_path(cls, value: str) -> str:
        return normalize_repository_path(value)

    @field_validator("source_hash")
    @classmethod
    def _validate_source_hash(cls, value: str) -> str:
        return require_sha256(value, "source_hash")

    @field_validator("module")
    @classmethod
    def _normalize_module(cls, value: str) -> str:
        return _nfc(value.strip())

    @field_validator("alias")
    @classmethod
    def _normalize_alias(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        normalized = _nfc(value.strip())
        if not normalized:
            raise ValueError("Import alias must not be empty when provided.")
        return normalized

    @field_validator("imported_names")
    @classmethod
    def _validate_imported_names(cls, values: List[str]) -> List[str]:
        normalized_names = []
        for name in values:
            normalized = _nfc(name.strip())
            if not normalized:
                raise ValueError("Imported names must not be empty.")
            normalized_names.append(normalized)
        return normalized_names

    @model_validator(mode="after")
    def _validate_import(self) -> "ImportReference":
        if not self.module and not self.imported_names:
            raise ValueError("An import must name a module or at least one imported name.")
        validate_source_span(
            self.start_line,
            self.end_line,
            self.start_column,
            self.end_column,
            require_columns=True,
            required=True,
        )
        return self


class CallSite(_GraphModel):
    """A syntactic call site with its exact source span."""

    relative_path: str
    callee_name: str
    receiver: Optional[str] = None
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)
    start_column: int = Field(ge=1)
    end_column: int = Field(ge=1)
    source_hash: str

    @field_validator("relative_path")
    @classmethod
    def _validate_relative_path(cls, value: str) -> str:
        return normalize_repository_path(value)

    @field_validator("source_hash")
    @classmethod
    def _validate_source_hash(cls, value: str) -> str:
        return require_sha256(value, "source_hash")

    @field_validator("callee_name", "receiver")
    @classmethod
    def _validate_text(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        normalized = _nfc(value.strip())
        if not normalized:
            raise ValueError("Callee name and receiver must not be empty when provided.")
        return normalized

    @model_validator(mode="after")
    def _validate_call_span(self) -> "CallSite":
        validate_source_span(
            self.start_line,
            self.end_line,
            self.start_column,
            self.end_column,
            require_columns=True,
            required=True,
        )
        return self


__all__ = [
    "CODE_GRAPH_SCHEMA_VERSION",
    "IDENTITY_VERSION",
    "NodeKind",
    "SymbolKind",
    "EdgeKind",
    "ResolutionKind",
    "EvidenceConfidence",
    "ProvenanceKind",
    "GraphBuildStatus",
    "DiagnosticSeverity",
    "GraphDiagnostic",
    "RepositoryNode",
    "FileNode",
    "SymbolNode",
    "GraphEdge",
    "CodeGraph",
    "GraphBuildResult",
    "GraphValidationResult",
    "LanguageCoverage",
    "SourceFile",
    "SymbolDeclaration",
    "ImportReference",
    "CallSite",
    "canonical_json",
    "sha256_hex",
    "require_sha256",
    "normalize_repository_path",
    "normalize_origin",
    "compute_repository_id",
    "compute_file_id",
    "compute_symbol_id",
    "compute_edge_id",
    "validate_source_span",
]
