"""
Phase 8.2 — Local Embedding Store.

Lightweight file-based persistence (JSONL). No PostgreSQL, Redis, Chroma,
Pinecone, Weaviate, pgvector, or FAISS.
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Dict, List, Optional

from .record import EmbeddingRecord


DEFAULT_STORE_FILENAME = "embeddings.jsonl"


class EmbeddingStore:
    """Append-and-rewrite JSONL store of embedding records."""

    def __init__(self, store_path: str):
        self.store_path = str(store_path)
        self._records: Dict[str, EmbeddingRecord] = {}
        self._load()

    # -- lifecycle ----------------------------------------------------

    def _load(self) -> None:
        path = Path(self.store_path)
        if not path.exists():
            return
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    payload = json.loads(line)
                    record = EmbeddingRecord(**payload)
                except Exception:
                    # Corrupt line — skip it rather than failing the whole store.
                    continue
                self._records[record.chunk_id] = record

    def _persist(self) -> None:
        path = Path(self.store_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        # Write atomically via a temp file in the same directory.
        fd, tmp_path = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                for record in self._records.values():
                    handle.write(record.model_dump_json() + "\n")
            os.replace(tmp_path, str(path))
        except Exception:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
            raise

    # -- interface ----------------------------------------------------

    def save(self, record: EmbeddingRecord) -> EmbeddingRecord:
        """Save (or replace) an embedding record."""
        self._records[record.chunk_id] = record
        self._persist()
        return record

    def get(self, chunk_id: str) -> Optional[EmbeddingRecord]:
        """Return the stored record for a chunk, or None."""
        return self._records.get(chunk_id)

    def check_reusable(
        self,
        chunk_id: str,
        content_hash: str,
        model_name: str,
        dimension: int,
    ) -> Optional[EmbeddingRecord]:
        """
        Return a reusable record, or None.

        Reuse requires matching chunk_id, content_hash, model_name, and dimension.
        """
        record = self._records.get(chunk_id)
        if record is None:
            return None
        if record.is_reusable_for(chunk_id, content_hash, model_name, dimension):
            return record
        return None

    def update(self, record: EmbeddingRecord) -> EmbeddingRecord:
        """Replace an existing record (same semantics as save)."""
        return self.save(record)

    def delete(self, chunk_id: str) -> bool:
        """Delete a stored record. Returns True if something was removed."""
        if chunk_id not in self._records:
            return False
        del self._records[chunk_id]
        self._persist()
        return True

    def delete_stale(
        self,
        active_chunk_ids: List[str],
        model_name: Optional[str] = None,
    ) -> List[str]:
        """
        Delete records that are no longer active (and optionally belong to
        another model). Returns the list of removed chunk_ids.
        """
        active = set(active_chunk_ids)
        removed: List[str] = []
        for chunk_id in list(self._records.keys()):
            record = self._records[chunk_id]
            if chunk_id not in active or (model_name and record.model_name != model_name):
                del self._records[chunk_id]
                removed.append(chunk_id)
        if removed:
            self._persist()
        return removed

    def list_all(self) -> List[EmbeddingRecord]:
        """Return all stored records (deterministic order by chunk_id)."""
        return [self._records[key] for key in sorted(self._records.keys())]

    def __len__(self) -> int:
        return len(self._records)
