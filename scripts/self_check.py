"""Minimal stability self-check for migrations and vector index metadata."""

from __future__ import annotations

import sqlite3
import sys
import uuid
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = PROJECT_ROOT / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from migrations.migrate import DB_PATH, latest_migration_version, migrate_to_latest
from services.vector_store_service import DocumentVectorStore


def check_migrations_idempotent() -> None:
    first = migrate_to_latest()
    second = migrate_to_latest()
    latest = latest_migration_version()
    assert second == first, f"migrate_to_latest not idempotent: {first} vs {second}"
    assert second == latest, f"schema version not latest: {second} vs {latest}"

    conn = sqlite3.connect(DB_PATH)
    try:
        row = conn.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()
        assert row is not None, "meta.schema_version row missing"
        assert int(row[0]) == latest, f"DB schema_version != latest ({row[0]} vs {latest})"
    finally:
        conn.close()


def check_vector_metadata_mismatch() -> None:
    course_id = f"selfcheck_{uuid.uuid4().hex[:8]}"
    store = DocumentVectorStore(course_id=course_id)
    try:
        store._mark_index_incomplete()  # exercise mismatch path with supported metadata update
        status = store.get_index_status()
        assert status["compatible"] is False, "Expected mismatch to be detected as incompatible"
        assert status["reasons"], "Expected mismatch reasons to be present"
    finally:
        try:
            store.client.delete_collection(name=store.collection.name)
        except Exception:
            pass


def main() -> None:
    check_migrations_idempotent()
    check_vector_metadata_mismatch()
    print("self_check: OK")


if __name__ == "__main__":
    main()
