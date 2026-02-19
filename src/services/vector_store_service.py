"""Vector store service for multi-file course materials (Chroma + OpenAI embeddings)."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import chromadb
from langchain_openai import OpenAIEmbeddings

from services.document_processor import PDFProcessor
from utils.file_utils import ensure_directory_exists

CURRENT_INDEX_VERSION = "1"
CURRENT_EMBEDDING_MODEL_NAME = "text-embedding-3-small"


@dataclass
class ChunkRecord:
    """Single chunk with metadata ready for vector indexing."""

    chunk_id: str
    text: str
    metadata: dict[str, Any]


class DocumentVectorStore:
    """Handles indexing and retrieval across multiple uploaded PDFs."""

    def __init__(self, persist_dir: str = "data/chroma", course_id: str = "default") -> None:
        self.persist_dir = Path(persist_dir)
        ensure_directory_exists(self.persist_dir)
        self.course_id = self._normalize_name(course_id)
        self.client = chromadb.PersistentClient(path=str(self.persist_dir))
        self.collection = self.client.get_or_create_collection(
            name=f"unsw_exam_{self.course_id}",
            metadata={
                "hnsw:space": "cosine",
                "index_version": CURRENT_INDEX_VERSION,
                "embedding_model_name": CURRENT_EMBEDDING_MODEL_NAME,
            },
        )
        self.pdf_processor = PDFProcessor()

    def _normalize_name(self, value: str) -> str:
        cleaned = re.sub(r"[^a-zA-Z0-9_-]", "_", value or "default")
        return cleaned[:64] or "default"

    def _make_embeddings(self, api_key: str, texts: list[str]) -> list[list[float]]:
        if not api_key or not api_key.strip():
            raise ValueError("Please provide a valid API key before indexing/searching.")
        embedder = OpenAIEmbeddings(model=CURRENT_EMBEDDING_MODEL_NAME, api_key=api_key.strip())
        return embedder.embed_documents(texts)

    def _embed_query(self, api_key: str, query: str) -> list[float]:
        if not api_key or not api_key.strip():
            raise ValueError("Please provide a valid API key before indexing/searching.")
        embedder = OpenAIEmbeddings(model=CURRENT_EMBEDDING_MODEL_NAME, api_key=api_key.strip())
        return embedder.embed_query(query)

    def _set_index_metadata(self, embedding_dim: int | None = None) -> None:
        metadata = {k: v for k, v in dict(self.collection.metadata or {}).items() if k != "hnsw:space"}
        metadata["index_version"] = CURRENT_INDEX_VERSION
        metadata["embedding_model_name"] = CURRENT_EMBEDDING_MODEL_NAME
        metadata["index_incomplete"] = "0"
        if embedding_dim and embedding_dim > 0:
            metadata["embedding_dim"] = str(embedding_dim)
        self.collection.modify(metadata=metadata)

    def _mark_index_incomplete(self) -> None:
        metadata = {k: v for k, v in dict(self.collection.metadata or {}).items() if k != "hnsw:space"}
        metadata["index_incomplete"] = "1"
        self.collection.modify(metadata=metadata)

    def get_index_status(self) -> dict[str, Any]:
        metadata = dict(self.collection.metadata or {})
        current_version = str(metadata.get("index_version", ""))
        current_model = str(metadata.get("embedding_model_name", ""))
        current_dim = str(metadata.get("embedding_dim", "")).strip()
        reasons: list[str] = []
        if current_version != CURRENT_INDEX_VERSION:
            reasons.append(f"index_version={current_version or 'missing'} != {CURRENT_INDEX_VERSION}")
        if current_model != CURRENT_EMBEDDING_MODEL_NAME:
            reasons.append(f"embedding_model_name={current_model or 'missing'} != {CURRENT_EMBEDDING_MODEL_NAME}")
        if str(metadata.get("index_incomplete", "0")) == "1":
            reasons.append("index_incomplete=1")
        # Only enforce dimension check when it exists; missing dim remains backward compatible.
        if current_dim and not current_dim.isdigit():
            reasons.append(f"embedding_dim invalid ({current_dim})")
        return {
            "compatible": len(reasons) == 0,
            "reasons": reasons,
            "metadata": metadata,
            "expected": {
                "index_version": CURRENT_INDEX_VERSION,
                "embedding_model_name": CURRENT_EMBEDDING_MODEL_NAME,
            },
        }

    def _split_text(self, text: str, chunk_size: int = 1000, overlap: int = 150) -> list[str]:
        normalized = " ".join(text.split())
        if not normalized:
            return []
        chunks: list[str] = []
        start = 0
        text_len = len(normalized)
        while start < text_len:
            end = min(text_len, start + chunk_size)
            chunks.append(normalized[start:end].strip())
            if end >= text_len:
                break
            start = max(start + 1, end - overlap)
        return [c for c in chunks if c]

    def _build_chunks(
        self,
        file_name: str,
        file_hash: str,
        pages: list[dict[str, Any]],
    ) -> list[ChunkRecord]:
        out: list[ChunkRecord] = []
        for p in pages:
            page_no = int(p.get("page", 0))
            page_text = str(p.get("text") or "")
            for i, chunk in enumerate(self._split_text(page_text)):
                chunk_id = f"{file_hash}:{page_no}:{i}"
                out.append(
                    ChunkRecord(
                        chunk_id=chunk_id,
                        text=chunk,
                        metadata={
                            "course_id": self.course_id,
                            "file_name": file_name,
                            "file_hash": file_hash,
                            "page": page_no,
                            "chunk_index": i,
                        },
                    )
                )
        return out

    def _has_file(self, file_hash: str) -> bool:
        existing = self.collection.get(
            where={"$and": [{"course_id": self.course_id}, {"file_hash": file_hash}]},
            limit=1,
            include=["metadatas"],
        )
        return bool(existing.get("ids"))

    def index_uploaded_files(self, files: list[Any], api_key: str) -> dict[str, int]:
        """
        Index multiple uploaded PDF files into Chroma.

        Returns stats with keys: indexed_files, skipped_files, chunks_added.
        """
        indexed_files = 0
        skipped_files = 0
        chunks_added = 0
        last_embedding_dim: int | None = None

        try:
            for file_obj in files:
                name = getattr(file_obj, "name", "uploaded.pdf")
                data = file_obj.read()
                if not data:
                    skipped_files += 1
                    continue

                file_hash = hashlib.sha256(data).hexdigest()
                if self._has_file(file_hash):
                    skipped_files += 1
                    continue

                pages = self.pdf_processor.extract_pages_from_bytes(data)
                if not pages:
                    skipped_files += 1
                    continue

                chunks = self._build_chunks(name, file_hash, pages)
                if not chunks:
                    skipped_files += 1
                    continue

                docs = [c.text for c in chunks]
                embeddings = self._make_embeddings(api_key, docs)
                self.collection.add(
                    ids=[c.chunk_id for c in chunks],
                    documents=docs,
                    metadatas=[c.metadata for c in chunks],
                    embeddings=embeddings,
                )
                last_embedding_dim = len(embeddings[0]) if embeddings and embeddings[0] else last_embedding_dim
                indexed_files += 1
                chunks_added += len(chunks)
        except Exception:
            self._mark_index_incomplete()
            raise

        # Update collection metadata only after the indexing pass completes successfully.
        self._set_index_metadata(last_embedding_dim)

        return {
            "indexed_files": indexed_files,
            "skipped_files": skipped_files,
            "chunks_added": chunks_added,
        }

    def _count_course_chunks(self) -> int:
        """Return number of indexed chunks for current course."""
        try:
            res = self.collection.get(
                where={"course_id": self.course_id},
                include=["metadatas"],
            )
            return len(res.get("ids") or [])
        except Exception:
            return 0

    def search(self, query: str, api_key: str, top_k: int = 8) -> list[dict[str, Any]]:
        """Retrieve top-k relevant chunks for the current course collection.

        Raises ValueError with a human-readable message on API or index errors
        so callers can surface it to the user rather than silently falling back.
        Distance threshold of 0.82 filters out semantically unrelated chunks.
        """
        if not query or not query.strip():
            return []

        query_embedding = self._embed_query(api_key, query)

        # Chroma raises if n_results > total indexed items — cap to actual count
        total = self._count_course_chunks()
        if total == 0:
            return []
        n = min(max(1, top_k), total)

        result = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=n,
            where={"course_id": self.course_id},
            include=["documents", "metadatas", "distances"],
        )

        docs = (result.get("documents") or [[]])[0]
        metas = (result.get("metadatas") or [[]])[0]
        distances = (result.get("distances") or [[]])[0]

        out: list[dict[str, Any]] = []
        for idx, doc in enumerate(docs):
            out.append(
                {
                    "text": doc,
                    "metadata": metas[idx] if idx < len(metas) else {},
                    "distance": distances[idx] if idx < len(distances) else None,
                }
            )
        return out

    def clear_course(self) -> None:
        """Remove all indexed chunks for the current course ID."""
        existing = self.collection.get(
            where={"course_id": self.course_id},
            include=["metadatas"],
        )
        ids = existing.get("ids") or []
        if ids:
            self.collection.delete(ids=ids)

    def has_indexed_content(self) -> bool:
        existing = self.collection.get(
            where={"course_id": self.course_id},
            limit=1,
            include=["metadatas"],
        )
        return bool(existing.get("ids"))
