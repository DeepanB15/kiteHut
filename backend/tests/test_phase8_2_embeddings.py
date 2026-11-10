"""
Phase 8.2 — Local Embedding Layer Tests.

Fully offline: no Ollama server required. Uses temporary stores.
Does NOT touch the user's real embedding data.
"""
import math
import tempfile
from pathlib import Path

import pytest

from app.chunking.model import CodeChunk, SymbolType
from app.embedding import (
    EmbeddingConfig,
    EmbeddingError,
    EmbeddingIndexer,
    EmbeddingProvider,
    EmbeddingRecord,
    EmbeddingStore,
    EmbeddingValidationError,
    FakeEmbeddingProvider,
    OllamaEmbeddingProvider,
    validate_vector,
)
from app.embedding.validation import validate_record


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def make_chunk(chunk_id="c1", content="def foo():\n    pass\n", file_path="a.py"):
    return CodeChunk(
        chunk_id=chunk_id,
        file_path=file_path,
        language="python",
        symbol_name="foo",
        symbol_type=SymbolType.FUNCTION,
        start_line=1,
        end_line=2,
        content=content,
        content_hash=CodeChunk.compute_hash(content),
    )


@pytest.fixture
def temp_store_path():
    tmp_dir = Path(tempfile.mkdtemp())
    try:
        yield str(tmp_dir / "embeddings.jsonl")
    finally:
        import shutil
        shutil.rmtree(tmp_dir, ignore_errors=True)


@pytest.fixture
def store(temp_store_path):
    return EmbeddingStore(temp_store_path)


@pytest.fixture
def provider():
    return FakeEmbeddingProvider(dimension=16)


# ------------------------------------------------------------------
# 1-2: Provider interface + config
# ------------------------------------------------------------------

def test_embedding_provider_interface(provider):
    assert isinstance(provider, EmbeddingProvider)
    vector = provider.embed_text("hello")
    assert isinstance(vector, list)
    assert len(vector) == provider.dimension


def test_local_provider_configuration_loads():
    config = EmbeddingConfig(provider="ollama", model="test-model")
    config.validate()
    assert config.model == "test-model"
    assert config.provider == "ollama"

    env_config = EmbeddingConfig.from_env()
    assert env_config.model  # non-empty
    assert env_config.provider


def test_ollama_provider_constructed_without_server():
    # Must construct without a running server; dimension unknown until first embed.
    p = OllamaEmbeddingProvider(EmbeddingConfig(provider="ollama", model="nomic-embed-text"))
    assert p.model_name == "nomic-embed-text"
    with pytest.raises(EmbeddingError):
        _ = p.dimension


# ------------------------------------------------------------------
# 3-4: Embedding record
# ------------------------------------------------------------------

def test_embedding_record_created():
    record = EmbeddingRecord(
        chunk_id="c1",
        content_hash="h1",
        model_name="m",
        dimension=3,
        vector=[0.1, 0.2, 0.3],
    )
    assert record.chunk_id == "c1"
    assert record.content_hash == "h1"
    assert record.model_name == "m"
    assert record.dimension == 3
    assert len(record.vector) == 3


def test_vector_dimension_recorded(provider):
    vector = provider.embed_text("x")
    record = EmbeddingRecord(
        chunk_id="c1", content_hash="h", model_name=provider.model_name,
        dimension=len(vector), vector=vector,
    )
    assert record.dimension == len(record.vector)


# ------------------------------------------------------------------
# 5-8: Validation
# ------------------------------------------------------------------

def test_valid_vector_passes():
    out = validate_vector([0.1, 0.2, 0.3], dimension=3)
    assert out == [0.1, 0.2, 0.3]


def test_empty_vector_rejected():
    with pytest.raises(EmbeddingValidationError):
        validate_vector([])


def test_non_numeric_vector_rejected():
    with pytest.raises(EmbeddingValidationError):
        validate_vector(["a", "b"])
    with pytest.raises(EmbeddingValidationError):
        validate_vector([1.0, None])


def test_nan_rejected():
    with pytest.raises(EmbeddingValidationError):
        validate_vector([float("nan"), 1.0])
    with pytest.raises(EmbeddingValidationError):
        validate_vector([float("inf"), 1.0])


def test_dimension_mismatch_rejected():
    with pytest.raises(EmbeddingValidationError):
        validate_vector([0.1, 0.2], dimension=3)


def test_validate_record_checks_dimension():
    record = EmbeddingRecord(chunk_id="c", content_hash="h", model_name="m", dimension=3, vector=[0.1])
    with pytest.raises(EmbeddingValidationError):
        validate_record(record)


def test_missing_vector_rejected():
    with pytest.raises(EmbeddingValidationError):
        validate_vector(None)


# ------------------------------------------------------------------
# 9-10: Persistence
# ------------------------------------------------------------------

def test_embedding_persists(store, provider, temp_store_path):
    record = EmbeddingRecord(
        chunk_id="c1", content_hash="h", model_name=provider.model_name,
        dimension=provider.dimension, vector=provider.embed_text("x"),
    )
    store.save(record)
    # Reload from disk
    reloaded = EmbeddingStore(temp_store_path)
    assert reloaded.get("c1") is not None
    assert reloaded.get("c1").content_hash == "h"


def test_stored_embedding_retrieved(store, provider):
    vector = provider.embed_text("x")
    store.save(EmbeddingRecord(chunk_id="c1", content_hash="h",
                               model_name=provider.model_name,
                               dimension=provider.dimension, vector=vector))
    got = store.get("c1")
    assert got.vector == vector


def test_store_list_and_delete(store, provider):
    for cid in ("c1", "c2"):
        store.save(EmbeddingRecord(chunk_id=cid, content_hash="h",
                                   model_name=provider.model_name,
                                   dimension=provider.dimension,
                                   vector=provider.embed_text(cid)))
    assert len(store.list_all()) == 2
    assert store.delete("c1") is True
    assert store.get("c1") is None
    assert store.delete("c1") is False


# ------------------------------------------------------------------
# 11-15: Reuse semantics
# ------------------------------------------------------------------

def test_same_hash_reuses(store, provider):
    indexer = EmbeddingIndexer(store=store, provider=provider)
    chunk = make_chunk()
    summary1 = indexer.index_chunks([chunk])
    assert summary1.generated == 1
    assert summary1.reused == 0

    summary2 = indexer.index_chunks([chunk])
    assert summary2.reused == 1
    assert summary2.generated == 0


def test_changed_content_regenerates(store, provider):
    indexer = EmbeddingIndexer(store=store, provider=provider)
    chunk = make_chunk(content="def foo():\n    return 1\n")
    indexer.index_chunks([chunk])
    changed = make_chunk(content="def foo():\n    return 2\n")
    summary = indexer.index_chunks([changed])
    assert summary.generated == 1
    assert summary.reused == 0


def test_model_change_regenerates(store, provider):
    indexer = EmbeddingIndexer(store=store, provider=provider)
    chunk = make_chunk()
    indexer.index_chunks([chunk])

    other = FakeEmbeddingProvider(dimension=16)
    other._dimension = 16
    other.config.model = "other-model"

    class OtherModelProvider(FakeEmbeddingProvider):
        @property
        def model_name(self):
            return "other-embedding-model"

    indexer2 = EmbeddingIndexer(store=store, provider=OtherModelProvider(dimension=16))
    summary = indexer2.index_chunks([chunk])
    assert summary.generated == 1
    assert summary.reused == 0
    assert store.get(chunk.chunk_id).model_name == "other-embedding-model"


def test_dimension_mismatch_prevents_reuse(store, provider):
    indexer = EmbeddingIndexer(store=store, provider=provider)
    chunk = make_chunk()
    indexer.index_chunks([chunk])

    class WiderProvider(FakeEmbeddingProvider):
        @property
        def model_name(self):
            return provider.model_name

    wider = WiderProvider(dimension=32)
    indexer2 = EmbeddingIndexer(store=store, provider=wider)
    # Content hash and model match, but dimension differs → must regenerate
    summary = indexer2.index_chunks([chunk])
    assert summary.generated == 1
    assert store.get(chunk.chunk_id).dimension == 32


def test_missing_embedding_generates(store, provider):
    indexer = EmbeddingIndexer(store=store, provider=provider)
    chunk = make_chunk(chunk_id="brand-new")
    summary = indexer.index_chunks([chunk])
    assert summary.generated == 1
    assert store.get("brand-new") is not None


def test_check_reusable_helper(store, provider):
    store.save(EmbeddingRecord(chunk_id="c1", content_hash="h1",
                               model_name="m", dimension=4, vector=[1.0, 2, 3, 4]))
    assert store.check_reusable("c1", "h1", "m", 4) is not None
    assert store.check_reusable("c1", "h2", "m", 4) is None
    assert store.check_reusable("c1", "h1", "m2", 4) is None
    assert store.check_reusable("c1", "h1", "m", 8) is None
    assert store.check_reusable("nope", "h1", "m", 4) is None


# ------------------------------------------------------------------
# 16: Failure handling
# ------------------------------------------------------------------

def test_failed_embedding_does_not_corrupt_store(store, provider):
    indexer = EmbeddingIndexer(store=store, provider=provider)
    good = make_chunk(chunk_id="good")
    indexer.index_chunks([good])

    class FailingProvider(FakeEmbeddingProvider):
        def embed_text(self, text):
            raise EmbeddingError("simulated failure")

    failing = FailingProvider(dimension=16)
    indexer2 = EmbeddingIndexer(store=store, provider=failing)
    bad = make_chunk(chunk_id="bad", content="other content")
    summary = indexer2.index_chunks([bad])

    assert summary.failed == 1
    assert summary.generated == 0
    # Existing record preserved
    assert store.get("good") is not None
    assert store.get("bad") is None


def test_invalid_provider_response_rejected(store):
    class BadProvider(FakeEmbeddingProvider):
        def embed_text(self, text):
            return [float("nan")] * 8

    indexer = EmbeddingIndexer(store=store, provider=BadProvider(dimension=8))
    summary = indexer.index_chunks([make_chunk(chunk_id="nan")])
    assert summary.failed == 1
    assert store.get("nan") is None


def test_no_zero_vector_substitution(store):
    class ZeroProvider(FakeEmbeddingProvider):
        def embed_text(self, text):
            return []

    indexer = EmbeddingIndexer(store=store, provider=ZeroProvider(dimension=8))
    summary = indexer.index_chunks([make_chunk(chunk_id="zero")])
    assert summary.failed == 1
    assert store.get("zero") is None


# ------------------------------------------------------------------
# 17: Batch embedding
# ------------------------------------------------------------------

def test_batch_embedding(provider):
    vectors = provider.embed_texts(["a", "b", "c"])
    assert len(vectors) == 3
    assert all(len(v) == provider.dimension for v in vectors)
    # Deterministic — same text → same vector
    assert provider.embed_texts(["a"])[0] == vectors[0]


def test_batch_embedding_empty(provider):
    assert provider.embed_texts([]) == []


def test_index_multiple_chunks(store, provider):
    indexer = EmbeddingIndexer(store=store, provider=provider)
    import uuid
    chunks = [make_chunk(chunk_id=f"c{i}-{uuid.uuid4().hex[:6]}", content=f"def f{i}(): pass\n") for i in range(5)]
    summary = indexer.index_chunks(chunks)
    assert summary.total == 5
    assert summary.generated == 5
    assert summary.failed == 0
    assert len(store.list_all()) == 5


# ------------------------------------------------------------------
# 18: Indexing summary
# ------------------------------------------------------------------

def test_indexing_summary_reports(store, provider):
    indexer = EmbeddingIndexer(store=store, provider=provider)
    chunks = [make_chunk(chunk_id=f"c{i}", content=f"def f{i}(): pass\n") for i in range(3)]
    first = indexer.index_chunks(chunks)
    assert first.to_dict() == {"total": 3, "reused": 0, "generated": 3, "failed": 0}

    second = indexer.index_chunks(chunks)
    assert second.to_dict() == {"total": 3, "reused": 3, "generated": 0, "failed": 0}


# ------------------------------------------------------------------
# 19-22: Phase 8.1 metadata intact + offline guarantees
# ------------------------------------------------------------------

def test_phase8_1_chunk_metadata_intact():
    chunk = make_chunk()
    assert chunk.symbol_name == "foo"
    assert chunk.symbol_type == SymbolType.FUNCTION
    assert chunk.parent_symbol is None
    assert chunk.file_path == "a.py"
    assert chunk.start_line == 1 and chunk.end_line == 2


def test_embedding_record_retains_chunk_identity(store, provider):
    chunk = make_chunk()
    indexer = EmbeddingIndexer(store=store, provider=provider)
    indexer.index_chunks([chunk])
    record = indexer.get_embedding(chunk.chunk_id)
    assert record.chunk_id == chunk.chunk_id
    assert record.content_hash == chunk.content_hash
    assert record.model_name == provider.model_name
    assert record.dimension == provider.dimension


def test_no_ollama_required_standard_tests():
    """The standard test path must never contact a local Ollama server."""
    # FakeEmbeddingProvider works with no server at all.
    p = FakeEmbeddingProvider(dimension=8)
    assert len(p.embed_text("hello")) == 8


def test_fake_provider_deterministic():
    a = FakeEmbeddingProvider(dimension=32).embed_text("stable input")
    b = FakeEmbeddingProvider(dimension=32).embed_text("stable input")
    assert a == b
    c = FakeEmbeddingProvider(dimension=32).embed_text("different input")
    assert a != c
    assert all(isinstance(v, float) and math.isfinite(v) for v in a)


def test_delete_stale_embeddings(store, provider):
    for cid in ("keep", "drop"):
        store.save(EmbeddingRecord(chunk_id=cid, content_hash="h",
                                   model_name=provider.model_name,
                                   dimension=provider.dimension,
                                   vector=provider.embed_text(cid)))
    removed = store.delete_stale(["keep"], model_name=provider.model_name)
    assert removed == ["drop"]
    assert store.get("keep") is not None
    assert store.get("drop") is None


def test_store_survives_corrupt_line(temp_store_path):
    Path(temp_store_path).write_text("not json\n", encoding="utf-8")
    store = EmbeddingStore(temp_store_path)
    assert len(store.list_all()) == 0
