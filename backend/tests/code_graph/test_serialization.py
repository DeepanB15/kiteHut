"""Phase 11.7 — focused tests for the serialization helpers."""

from __future__ import annotations

import json
from pathlib import Path

from app.code_graph.builder import CodeGraphBuilder
from app.code_graph.models import (
    CODE_GRAPH_SCHEMA_VERSION,
    DiagnosticSeverity,
    GraphBuildStatus,
)
from app.code_graph.serialization import (
    build_and_serialize,
    deserialize_graph_json,
    serialize_graph_json,
    write_graph_file,
)


def _write(root: Path, relative_path: str, content: str) -> Path:
    path = root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def _build_graph(tmp_path: Path):
    _write(tmp_path, "pkg/__init__.py", "\n")
    _write(tmp_path, "pkg/core.py", "def run():\n    return 1\n")
    result = CodeGraphBuilder(tmp_path).build()
    assert result.graph is not None
    return result.graph


# ------------------------------------------------------------- round trip ---


def test_round_trip_preserves_graph(tmp_path: Path) -> None:
    graph = _build_graph(tmp_path)
    payload = serialize_graph_json(graph)

    loaded, validation = deserialize_graph_json(payload)

    assert validation.valid is True
    assert loaded is not None
    assert [f.id for f in loaded.files] == [f.id for f in graph.files]
    assert [s.id for s in loaded.symbols] == [s.id for s in graph.symbols]
    assert [e.id for e in loaded.edges] == [e.id for e in graph.edges]
    assert loaded.source_digest == graph.source_digest
    assert loaded.repository == graph.repository
    assert loaded.schema_version == CODE_GRAPH_SCHEMA_VERSION


def test_serialization_is_byte_identical_for_repeated_calls(tmp_path: Path) -> None:
    graph = _build_graph(tmp_path)
    first = serialize_graph_json(graph)
    second = serialize_graph_json(graph)
    assert first == second


def test_serialization_has_no_absolute_machine_paths(tmp_path: Path) -> None:
    graph = _build_graph(tmp_path)
    payload = serialize_graph_json(graph)
    assert str(tmp_path.resolve()) not in payload


def test_serialized_payload_is_canonical_json(tmp_path: Path) -> None:
    graph = _build_graph(tmp_path)
    payload = serialize_graph_json(graph)
    # Keys sorted, compact separators, UTF-8 output.
    parsed = json.loads(payload)
    assert list(parsed.keys()) == sorted(parsed.keys())
    assert '": ' not in payload
    assert payload.encode("utf-8")


def test_deserialize_rejects_malformed_json(tmp_path: Path) -> None:
    graph, validation = deserialize_graph_json("{not json")
    assert graph is None
    assert validation.valid is False
    assert validation.errors[0].code == "graph_parse_error"
    assert validation.errors[0].severity == DiagnosticSeverity.FATAL


def test_deserialize_rejects_non_object_payload() -> None:
    graph, validation = deserialize_graph_json("[1, 2, 3]")
    assert graph is None
    assert validation.errors[0].code == "graph_parse_error"


def test_deserialize_rejects_unknown_schema_version(tmp_path: Path) -> None:
    graph = _build_graph(tmp_path)
    payload = json.loads(serialize_graph_json(graph))
    payload["schema_version"] = "codegraph:v999"
    tampered = json.dumps(payload, sort_keys=True, separators=(",", ":"))

    loaded, validation = deserialize_graph_json(tampered)
    assert loaded is None
    assert validation.errors[0].code == "graph_schema_incompatible"


def test_deserialize_rejects_payload_missing_schema_version(tmp_path: Path) -> None:
    graph = _build_graph(tmp_path)
    payload = json.loads(serialize_graph_json(graph))
    payload.pop("schema_version")
    tampered = json.dumps(payload, sort_keys=True, separators=(",", ":"))

    loaded, validation = deserialize_graph_json(tampered)
    assert loaded is None
    assert validation.errors[0].code == "graph_schema_incompatible"


# ------------------------------------------------------------- file I/O ----


def test_write_graph_file_round_trips_through_disk(tmp_path: Path) -> None:
    graph = _build_graph(tmp_path)
    output = tmp_path / "out" / "graph.json"

    success, diagnostics = write_graph_file(graph, output)

    assert success is True
    assert diagnostics == []
    loaded, validation = deserialize_graph_json(output.read_text(encoding="utf-8"))
    assert validation.valid is True
    assert loaded is not None
    assert [f.id for f in loaded.files] == [f.id for f in graph.files]


def test_write_graph_file_refuses_to_clobber_unrelated_file(tmp_path: Path) -> None:
    graph = _build_graph(tmp_path)
    target = tmp_path / "unrelated.txt"
    target.write_text("not a graph", encoding="utf-8")

    success, diagnostics = write_graph_file(graph, target)

    assert success is False
    assert diagnostics[0].code == "unrelated_file_exists"
    assert target.read_text(encoding="utf-8") == "not a graph"


def test_write_graph_file_refuses_invalid_graph(tmp_path: Path) -> None:
    graph = _build_graph(tmp_path)
    # Mutate a field in place to make the graph invalid for the writer.
    graph.files[0].content_hash = "0" * 64
    output = tmp_path / "graph.json"

    success, diagnostics = write_graph_file(graph, output)

    assert success is False
    assert diagnostics  # validator diagnostics surfaced
    assert not output.exists()


# ------------------------------------------------------- end to end build --


def test_build_and_serialize_writes_output(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    _write(repo, "mod.py", "def f():\n    return 1\n")
    output = tmp_path / "snapshot.json"

    graph, result = build_and_serialize(CodeGraphBuilder(repo), output)

    assert graph is not None
    assert result.status == GraphBuildStatus.COMPLETE
    assert output.exists()


def test_build_and_serialize_does_not_write_on_failed_build(tmp_path: Path) -> None:
    output = tmp_path / "snapshot.json"

    graph, result = build_and_serialize(
        CodeGraphBuilder(tmp_path / "missing-root"), output
    )

    assert graph is None
    assert result.status == GraphBuildStatus.FAILED
    assert not output.exists()
