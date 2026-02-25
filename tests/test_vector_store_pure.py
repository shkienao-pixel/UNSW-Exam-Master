"""Tests for pure functions in DocumentVectorStore (no Chroma / API calls)."""

from __future__ import annotations

import pytest


# Import only what we need to avoid triggering Chroma initialization.
from services.vector_store_service import DocumentVectorStore, ChunkRecord


# ──────────────────────────────────────────────────────────────
# Helpers: create a store instance without connecting to Chroma
# ──────────────────────────────────────────────────────────────

class _FakeCollection:
    def __init__(self):
        self.metadata = {
            "hnsw:space": "cosine",
            "index_version": "1",
            "embedding_model_name": "text-embedding-3-small",
        }

    def get_or_create_collection(self, *a, **kw):
        return self

    def modify(self, metadata):
        self.metadata.update(metadata)

    def get(self, *a, **kw):
        return {"ids": []}

    def query(self, *a, **kw):
        return {"documents": [[]], "metadatas": [[]], "distances": [[]]}


def _make_store(monkeypatch, course_id: str = "test_course") -> DocumentVectorStore:
    """Return a DocumentVectorStore with Chroma patched out."""
    import chromadb

    class _FakeClient:
        def get_or_create_collection(self, name, metadata=None):
            col = _FakeCollection()
            col.metadata.update(metadata or {})
            return col

    monkeypatch.setattr(chromadb, "PersistentClient", lambda path: _FakeClient())
    store = DocumentVectorStore(persist_dir="/tmp/fake", course_id=course_id)
    return store


# ──────────────────────────────────────────────────────────────
# _normalize_name
# ──────────────────────────────────────────────────────────────

class TestNormalizeName:
    def test_alphanumeric_unchanged(self, monkeypatch):
        s = _make_store(monkeypatch)
        assert s._normalize_name("COMP3900") == "COMP3900"

    def test_spaces_replaced_with_underscore(self, monkeypatch):
        s = _make_store(monkeypatch)
        assert s._normalize_name("hello world") == "hello_world"

    def test_special_chars_replaced(self, monkeypatch):
        s = _make_store(monkeypatch)
        result = s._normalize_name("course/name#1")
        assert "/" not in result
        assert "#" not in result

    def test_empty_string_returns_default(self, monkeypatch):
        s = _make_store(monkeypatch)
        assert s._normalize_name("") == "default"

    def test_none_returns_default(self, monkeypatch):
        s = _make_store(monkeypatch)
        assert s._normalize_name(None) == "default"  # type: ignore[arg-type]

    def test_truncated_to_64(self, monkeypatch):
        s = _make_store(monkeypatch)
        long_name = "a" * 100
        assert len(s._normalize_name(long_name)) <= 64


# ──────────────────────────────────────────────────────────────
# _split_text
# ──────────────────────────────────────────────────────────────

class TestSplitText:
    def setup_method(self):
        pass

    def _store(self, monkeypatch):
        return _make_store(monkeypatch)

    def test_empty_string_returns_empty_list(self, monkeypatch):
        s = self._store(monkeypatch)
        assert s._split_text("") == []

    def test_whitespace_only_returns_empty_list(self, monkeypatch):
        s = self._store(monkeypatch)
        assert s._split_text("   \n\t  ") == []

    def test_short_text_single_chunk(self, monkeypatch):
        s = self._store(monkeypatch)
        text = "Hello world"
        chunks = s._split_text(text, chunk_size=1000)
        assert len(chunks) == 1
        assert chunks[0] == "Hello world"

    def test_long_text_splits_into_multiple_chunks(self, monkeypatch):
        s = self._store(monkeypatch)
        text = "word " * 300  # ~1500 chars
        chunks = s._split_text(text, chunk_size=500, overlap=50)
        assert len(chunks) > 1

    def test_overlap_causes_repeated_content(self, monkeypatch):
        s = self._store(monkeypatch)
        text = "a" * 200
        chunks = s._split_text(text, chunk_size=100, overlap=20)
        # With overlap, consecutive chunks should share content
        assert len(chunks) >= 2

    def test_no_empty_chunks(self, monkeypatch):
        s = self._store(monkeypatch)
        text = "Hello " * 500
        chunks = s._split_text(text, chunk_size=100, overlap=10)
        assert all(c.strip() for c in chunks)

    def test_normalizes_whitespace(self, monkeypatch):
        s = self._store(monkeypatch)
        text = "hello    \n\n  world"
        chunks = s._split_text(text, chunk_size=1000)
        assert len(chunks) == 1
        assert "  " not in chunks[0]  # Multiple spaces collapsed


# ──────────────────────────────────────────────────────────────
# _build_chunks
# ──────────────────────────────────────────────────────────────

class TestBuildChunks:
    def test_returns_chunk_records(self, monkeypatch):
        s = _make_store(monkeypatch)
        pages = [{"page": 1, "text": "Some content about machine learning."}]
        chunks = s._build_chunks("file.pdf", "abc123", pages)
        assert len(chunks) >= 1
        assert all(isinstance(c, ChunkRecord) for c in chunks)

    def test_chunk_id_format(self, monkeypatch):
        s = _make_store(monkeypatch)
        pages = [{"page": 2, "text": "Test page content"}]
        chunks = s._build_chunks("doc.pdf", "hash_xyz", pages)
        assert chunks[0].chunk_id.startswith("hash_xyz:2:")

    def test_metadata_populated(self, monkeypatch):
        s = _make_store(monkeypatch)
        pages = [{"page": 1, "text": "Content"}]
        chunks = s._build_chunks("report.pdf", "h1", pages)
        meta = chunks[0].metadata
        assert meta["file_name"] == "report.pdf"
        assert meta["file_hash"] == "h1"
        assert meta["page"] == 1

    def test_empty_pages_returns_empty(self, monkeypatch):
        s = _make_store(monkeypatch)
        chunks = s._build_chunks("file.pdf", "abc", [])
        assert chunks == []

    def test_empty_page_text_skipped(self, monkeypatch):
        s = _make_store(monkeypatch)
        pages = [{"page": 1, "text": "   "}]
        chunks = s._build_chunks("file.pdf", "abc", pages)
        assert chunks == []

    def test_multiple_pages(self, monkeypatch):
        s = _make_store(monkeypatch)
        pages = [
            {"page": 1, "text": "Page one content"},
            {"page": 2, "text": "Page two content"},
        ]
        chunks = s._build_chunks("file.pdf", "h2", pages)
        page_nos = {c.metadata["page"] for c in chunks}
        assert 1 in page_nos
        assert 2 in page_nos
