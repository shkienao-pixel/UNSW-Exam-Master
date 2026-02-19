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
from services.course_workspace_service import (
    create_course,
    create_deck,
    create_output,
    create_scope_set,
    ensure_default_scope_set,
    list_artifacts,
    list_cards,
    list_courses,
    list_decks,
    list_outputs,
    list_scope_set_artifact_ids,
    list_scope_sets,
    replace_scope_set_items,
    save_artifact,
    replace_vocab_cards,
)
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


def _cleanup_test_course(course_id: str) -> None:
    """Delete a test course and all its related rows from the DB."""
    conn = sqlite3.connect(DB_PATH)
    try:
        # Delete in dependency order (children before parents).
        conn.execute(
            "DELETE FROM cards WHERE deck_id IN (SELECT id FROM decks WHERE course_id=?)",
            [course_id],
        )
        conn.execute("DELETE FROM decks WHERE course_id=?", [course_id])
        conn.execute(
            "DELETE FROM scope_set_items WHERE scope_set_id IN "
            "(SELECT id FROM scope_sets WHERE course_id=?)",
            [course_id],
        )
        conn.execute("DELETE FROM scope_sets WHERE course_id=?", [course_id])
        conn.execute("DELETE FROM outputs WHERE course_id=?", [course_id])
        conn.execute("DELETE FROM artifacts WHERE course_id=?", [course_id])
        conn.execute("DELETE FROM courses WHERE id=?", [course_id])
        conn.commit()
    finally:
        conn.close()


def check_workspace_tables_and_crud() -> None:
    expected_tables = {"courses", "artifacts", "outputs", "decks", "cards", "scope_sets", "scope_set_items"}
    conn = sqlite3.connect(DB_PATH)
    try:
        rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        tables = {str(r[0]) for r in rows}
        missing = expected_tables - tables
        assert not missing, f"missing workspace tables: {sorted(missing)}"
    finally:
        conn.close()

    unique_code = f"SC{uuid.uuid4().hex[:6].upper()}"
    course = create_course(unique_code, "Self Check Course")
    course_id = str(course["id"])
    try:
        assert any(c["id"] == course_id for c in list_courses()), "course create/list failed"

        out_id = create_output(course_id, "summary", "self check output")
        assert out_id > 0, "output insert failed"
        outputs = list_outputs(course_id)
        assert any(int(o["id"]) == out_id for o in outputs), "output list failed"
        created = next((o for o in outputs if int(o["id"]) == out_id), None)
        assert created is not None, "created output missing"
        assert "output_type" in created, "output_type column not surfaced"
        assert "scope_artifact_ids" in created, "scope_artifact_ids column not surfaced"
        assert "model_used" in created, "model_used column not surfaced"

        artifact = save_artifact(course_id, "selfcheck.pdf", b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF")
        aid = int(artifact["id"])
        default_scope = ensure_default_scope_set(course_id)
        assert default_scope.get("is_default") == 1, "default scope set missing"
        assert aid in (default_scope.get("artifact_ids") or []), "default scope set not synced with artifacts"

        custom_scope_id = create_scope_set(course_id, "Week 1")
        replace_scope_set_items(custom_scope_id, [aid])
        custom_items = list_scope_set_artifact_ids(custom_scope_id)
        assert custom_items == [aid], "scope_set_items replace/list failed"
        assert any(int(s["id"]) == custom_scope_id for s in list_scope_sets(course_id)), "scope_sets list failed"

        out_quiz_id = create_output(
            course_id,
            "quiz",
            "{\"quiz_title\":\"t\",\"questions\":[]}",
            scope_artifact_ids=[aid],
            scope_set_id=custom_scope_id,
        )
        assert out_quiz_id > 0, "quiz output insert failed"
        quiz_out = next((o for o in list_outputs(course_id) if int(o["id"]) == out_quiz_id), None)
        assert quiz_out is not None, "quiz output missing"
        assert quiz_out.get("scope_artifact_ids") == [aid], "scope_artifact_ids mismatch"
        assert int(quiz_out.get("scope_set_id") or 0) == custom_scope_id, "scope_set_id mismatch"

        deck_id = create_deck(course_id, "Self Check Deck", "vocab")
        assert deck_id > 0, "deck insert failed"
        assert any(int(d["id"]) == deck_id for d in list_decks(course_id)), "deck list failed"
        inserted = replace_vocab_cards(deck_id, course_id, [{"front": "A", "back": "B"}])
        assert inserted == 1, "card replace failed"
        assert len(list_cards(deck_id)) == 1, "card list failed"
    finally:
        # Always clean up the test course to prevent DB pollution across runs.
        _cleanup_test_course(course_id)


def main() -> None:
    check_migrations_idempotent()
    check_vector_metadata_mismatch()
    check_workspace_tables_and_crud()
    print("self_check: OK")


if __name__ == "__main__":
    main()
