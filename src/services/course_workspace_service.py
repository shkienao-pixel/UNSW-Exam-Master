"""Course workspace persistence services backed by SQLite."""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from migrations.migrate import DB_PATH
from utils.file_utils import ensure_directory_exists

PROJECT_ROOT = Path(__file__).resolve().parents[2]
COURSE_ARTIFACT_ROOT = PROJECT_ROOT / "data" / "courses"
VALID_DECK_TYPES = {"vocab", "mcq"}
VALID_OUTPUT_TYPES = {"summary", "graph", "outline", "syllabus", "quiz"}


class WorkspaceValidationError(ValueError):
    """Raised when workspace payload validation fails."""


def _now_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat()


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _normalize_course_code(code: str) -> str:
    normalized = re.sub(r"\s+", "", (code or "").strip().upper())
    if not normalized:
        raise WorkspaceValidationError("Course code is required.")
    if len(normalized) > 32:
        raise WorkspaceValidationError("Course code must be <= 32 characters.")
    if not re.fullmatch(r"[A-Z0-9_-]+", normalized):
        raise WorkspaceValidationError("Course code only allows A-Z, 0-9, underscore, hyphen.")
    return normalized


def _sanitize_file_name(file_name: str) -> str:
    clean = re.sub(r"[^a-zA-Z0-9._-]", "_", (file_name or "uploaded.pdf").strip())
    return clean[:128] or "uploaded.pdf"


def _row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {k: row[k] for k in row.keys()}


# ---------- Course ----------

def list_courses() -> list[dict[str, Any]]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT id, code, name, created_at, updated_at FROM courses ORDER BY code COLLATE NOCASE ASC"
        ).fetchall()
    return [_row_to_dict(r) or {} for r in rows]


def get_course(course_id: str) -> dict[str, Any] | None:
    if not course_id:
        return None
    with _connect() as conn:
        row = conn.execute(
            "SELECT id, code, name, created_at, updated_at FROM courses WHERE id=?",
            (course_id,),
        ).fetchone()
    return _row_to_dict(row)


def create_course(code: str, name: str) -> dict[str, Any]:
    normalized_code = _normalize_course_code(code)
    clean_name = (name or "").strip()
    if not clean_name:
        raise WorkspaceValidationError("Course name is required.")
    if len(clean_name) > 120:
        raise WorkspaceValidationError("Course name must be <= 120 characters.")

    course_id = str(uuid4())
    now = _now_iso()
    try:
        with _connect() as conn:
            conn.execute(
                """
                INSERT INTO courses(id, code, name, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (course_id, normalized_code, clean_name, now, now),
            )
    except sqlite3.IntegrityError as e:
        raise WorkspaceValidationError(f"Course code '{normalized_code}' already exists.") from e

    created = get_course(course_id)
    if created is None:
        raise WorkspaceValidationError("Failed to create course.")
    return created


# ---------- Artifacts ----------

def save_artifact(course_id: str, file_name: str, file_bytes: bytes) -> dict[str, Any]:
    if not course_id:
        raise WorkspaceValidationError("Active course is required before upload.")
    if not file_bytes:
        raise WorkspaceValidationError("Empty file cannot be saved.")

    digest = hashlib.sha256(file_bytes).hexdigest()
    clean_name = _sanitize_file_name(file_name)
    ensure_directory_exists(COURSE_ARTIFACT_ROOT / course_id / "artifacts")
    rel_path = Path("data") / "courses" / course_id / "artifacts" / f"{digest[:12]}_{clean_name}"
    abs_path = PROJECT_ROOT / rel_path
    if not abs_path.exists():
        abs_path.write_bytes(file_bytes)

    with _connect() as conn:
        existing = conn.execute(
            """
            SELECT id, course_id, file_name, file_hash, file_path, created_at
            FROM artifacts
            WHERE course_id=? AND file_hash=?
            """,
            (course_id, digest),
        ).fetchone()
        if existing is not None:
            return _row_to_dict(existing) or {}

        now = _now_iso()
        conn.execute(
            """
            INSERT INTO artifacts(course_id, file_name, file_hash, file_path, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (course_id, clean_name, digest, str(rel_path).replace("\\", "/"), now),
        )
        row = conn.execute(
            """
            SELECT id, course_id, file_name, file_hash, file_path, created_at
            FROM artifacts
            WHERE course_id=? AND file_hash=?
            """,
            (course_id, digest),
        ).fetchone()
    return _row_to_dict(row) or {}


def list_artifacts(course_id: str) -> list[dict[str, Any]]:
    if not course_id:
        return []
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT id, course_id, file_name, file_hash, file_path, created_at
            FROM artifacts
            WHERE course_id=?
            ORDER BY created_at DESC, id DESC
            """,
            (course_id,),
        ).fetchall()
    return [_row_to_dict(r) or {} for r in rows]


def list_artifacts_by_ids(course_id: str, artifact_ids: list[int]) -> list[dict[str, Any]]:
    if not course_id or not artifact_ids:
        return []
    normalized = sorted({int(x) for x in artifact_ids})
    placeholders = ",".join("?" for _ in normalized)
    with _connect() as conn:
        rows = conn.execute(
            f"""
            SELECT id, course_id, file_name, file_hash, file_path, created_at
            FROM artifacts
            WHERE course_id=? AND id IN ({placeholders})
            ORDER BY created_at DESC, id DESC
            """,
            (course_id, *normalized),
        ).fetchall()
    return [_row_to_dict(r) or {} for r in rows]


# ---------- Scope Sets ----------

def _create_scope_set_row(conn: sqlite3.Connection, course_id: str, name: str, is_default: int) -> int:
    now = _now_iso()
    cur = conn.execute(
        """
        INSERT INTO scope_sets(course_id, name, is_default, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (course_id, name.strip(), int(is_default), now, now),
    )
    return int(cur.lastrowid)


def list_scope_set_artifact_ids(scope_set_id: int) -> list[int]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT artifact_id FROM scope_set_items WHERE scope_set_id=? ORDER BY artifact_id ASC",
            (int(scope_set_id),),
        ).fetchall()
    out: list[int] = []
    for row in rows:
        try:
            out.append(int(row[0]))
        except (TypeError, ValueError):
            continue
    return out


def _replace_scope_set_items_conn(conn: sqlite3.Connection, scope_set_id: int, artifact_ids: list[int]) -> None:
    now = _now_iso()
    conn.execute("DELETE FROM scope_set_items WHERE scope_set_id=?", (int(scope_set_id),))
    unique_ids = sorted({int(x) for x in artifact_ids})
    for aid in unique_ids:
        conn.execute(
            """
            INSERT INTO scope_set_items(scope_set_id, artifact_id, created_at)
            VALUES (?, ?, ?)
            """,
            (int(scope_set_id), aid, now),
        )
    conn.execute("UPDATE scope_sets SET updated_at=? WHERE id=?", (now, int(scope_set_id)))


def get_scope_set(scope_set_id: int) -> dict[str, Any] | None:
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT id, course_id, name, is_default, created_at, updated_at
            FROM scope_sets
            WHERE id=?
            """,
            (int(scope_set_id),),
        ).fetchone()
    item = _row_to_dict(row)
    if not item:
        return None
    item["artifact_ids"] = list_scope_set_artifact_ids(int(item["id"]))
    return item


def ensure_default_scope_set(course_id: str) -> dict[str, Any]:
    if not course_id:
        raise WorkspaceValidationError("course_id is required")
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT id, course_id, name, is_default, created_at, updated_at
            FROM scope_sets
            WHERE course_id=? AND is_default=1
            ORDER BY id ASC
            LIMIT 1
            """,
            (course_id,),
        ).fetchone()
        if row is None:
            scope_set_id = _create_scope_set_row(conn, course_id, "All Materials", 1)
        else:
            scope_set_id = int(row["id"])

        artifacts = conn.execute(
            "SELECT id FROM artifacts WHERE course_id=? ORDER BY id ASC",
            (course_id,),
        ).fetchall()
        artifact_ids = [int(r[0]) for r in artifacts]
        _replace_scope_set_items_conn(conn, scope_set_id, artifact_ids)

    scope_set = get_scope_set(scope_set_id)
    if scope_set is None:
        raise WorkspaceValidationError("Failed to ensure default scope set.")
    return scope_set


def list_scope_sets(course_id: str) -> list[dict[str, Any]]:
    if not course_id:
        return []
    ensure_default_scope_set(course_id)
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT id, course_id, name, is_default, created_at, updated_at
            FROM scope_sets
            WHERE course_id=?
            ORDER BY is_default DESC, created_at ASC, id ASC
            """,
            (course_id,),
        ).fetchall()
    out: list[dict[str, Any]] = []
    for row in rows:
        item = _row_to_dict(row) or {}
        artifact_ids = list_scope_set_artifact_ids(int(item.get("id", 0)))
        item["artifact_ids"] = artifact_ids
        item["file_count"] = len(artifact_ids)
        out.append(item)
    return out


def create_scope_set(course_id: str, name: str) -> int:
    if not course_id:
        raise WorkspaceValidationError("Active course is required before creating scope set.")
    clean_name = (name or "").strip()
    if not clean_name:
        raise WorkspaceValidationError("Scope set name is required.")
    if len(clean_name) > 120:
        raise WorkspaceValidationError("Scope set name must be <= 120 characters.")
    try:
        with _connect() as conn:
            scope_set_id = _create_scope_set_row(conn, course_id, clean_name, 0)
    except sqlite3.IntegrityError as e:
        raise WorkspaceValidationError(f"Scope set '{clean_name}' already exists.") from e
    return scope_set_id


def rename_scope_set(scope_set_id: int, name: str) -> dict[str, Any]:
    scope_set = get_scope_set(scope_set_id)
    if not scope_set:
        raise WorkspaceValidationError("Scope set not found.")
    if int(scope_set.get("is_default", 0)) == 1:
        raise WorkspaceValidationError("Default scope set cannot be renamed.")

    clean_name = (name or "").strip()
    if not clean_name:
        raise WorkspaceValidationError("Scope set name is required.")
    if len(clean_name) > 120:
        raise WorkspaceValidationError("Scope set name must be <= 120 characters.")
    if clean_name == str(scope_set.get("name") or ""):
        return scope_set

    now = _now_iso()
    try:
        with _connect() as conn:
            conn.execute(
                "UPDATE scope_sets SET name=?, updated_at=? WHERE id=?",
                (clean_name, now, int(scope_set_id)),
            )
    except sqlite3.IntegrityError as e:
        raise WorkspaceValidationError(f"Scope set '{clean_name}' already exists.") from e

    updated = get_scope_set(int(scope_set_id))
    if not updated:
        raise WorkspaceValidationError("Failed to rename scope set.")
    return updated


def delete_scope_set(scope_set_id: int) -> None:
    scope_set = get_scope_set(scope_set_id)
    if not scope_set:
        raise WorkspaceValidationError("Scope set not found.")
    if int(scope_set.get("is_default", 0)) == 1:
        raise WorkspaceValidationError("Default scope set cannot be deleted.")
    with _connect() as conn:
        conn.execute("DELETE FROM scope_sets WHERE id=?", (int(scope_set_id),))


def replace_scope_set_items(scope_set_id: int, artifact_ids: list[int]) -> int:
    scope_set = get_scope_set(scope_set_id)
    if not scope_set:
        raise WorkspaceValidationError("Scope set not found.")
    with _connect() as conn:
        _replace_scope_set_items_conn(conn, int(scope_set_id), artifact_ids)
    return len(sorted({int(x) for x in artifact_ids}))


def resolve_scope_artifact_ids(course_id: str, scope_set_id: int) -> list[int]:
    if not course_id:
        return []
    scope_set = get_scope_set(scope_set_id)
    if not scope_set or str(scope_set.get("course_id") or "") != course_id:
        return []
    if int(scope_set.get("is_default", 0)) == 1:
        ensured = ensure_default_scope_set(course_id)
        return [int(x) for x in ensured.get("artifact_ids") or []]
    return [int(x) for x in (scope_set.get("artifact_ids") or [])]


# ---------- Outputs ----------

def _normalize_scope_artifact_ids(scope_artifact_ids: list[int] | None) -> str:
    if not scope_artifact_ids:
        return "[]"
    normalized = sorted({int(x) for x in scope_artifact_ids})
    return json.dumps(normalized, ensure_ascii=False)


def _parse_scope_artifact_ids(raw: Any) -> list[int]:
    if isinstance(raw, list):
        out: list[int] = []
        for x in raw:
            try:
                out.append(int(x))
            except (TypeError, ValueError):
                continue
        return out
    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            return []
        try:
            parsed = json.loads(text)
            return _parse_scope_artifact_ids(parsed)
        except json.JSONDecodeError:
            return []
    return []


def create_output(
    course_id: str,
    output_type: str,
    content: str,
    scope_artifact_ids: list[int] | None = None,
    scope_set_id: int | None = None,
    scope: str = "course",
    model_used: str = "gpt-4o",
    status: str = "success",
    path: str = "",
) -> int:
    if not course_id:
        raise WorkspaceValidationError("Active course is required before generating outputs.")
    out_type = (output_type or "").strip().lower()
    if out_type not in VALID_OUTPUT_TYPES:
        raise WorkspaceValidationError(f"Unsupported output type: {output_type}")

    now = _now_iso()
    scope_ids_json = _normalize_scope_artifact_ids(scope_artifact_ids)
    normalized_scope_set_id = int(scope_set_id) if scope_set_id is not None else None
    with _connect() as conn:
        cur = conn.execute(
            """
            INSERT INTO outputs(
                course_id,
                output_type,
                type,
                scope_set_id,
                scope_artifact_ids,
                scope,
                model_used,
                model,
                status,
                content,
                path,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                course_id,
                out_type,
                out_type,
                normalized_scope_set_id,
                scope_ids_json,
                scope,
                model_used,
                model_used,
                status,
                content,
                path,
                now,
            ),
        )
        return int(cur.lastrowid)


def _rows_to_outputs(rows: list[sqlite3.Row]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for row in rows:
        item = _row_to_dict(row) or {}
        scope_ids = _parse_scope_artifact_ids(item.get("scope_artifact_ids"))
        item["scope_artifact_ids"] = scope_ids
        item["scope_file_count"] = len(scope_ids)
        try:
            raw_scope_set_id = item.get("scope_set_id")
            item["scope_set_id"] = int(raw_scope_set_id) if raw_scope_set_id is not None else None
        except (TypeError, ValueError):
            item["scope_set_id"] = None
        out.append(item)
    return out


def list_outputs(course_id: str, output_type: str = "") -> list[dict[str, Any]]:
    if not course_id:
        return []
    normalized_type = output_type.strip().lower()
    with _connect() as conn:
        if normalized_type:
            rows = conn.execute(
                """
                SELECT
                    id,
                    course_id,
                    COALESCE(output_type, type) AS output_type,
                    COALESCE(type, output_type) AS type,
                    scope_set_id,
                    scope_artifact_ids,
                    scope,
                    COALESCE(model_used, model) AS model_used,
                    COALESCE(model, model_used) AS model,
                    status,
                    content,
                    path,
                    created_at
                FROM outputs
                WHERE course_id=? AND COALESCE(output_type, type)=?
                ORDER BY created_at DESC, id DESC
                """,
                (course_id, normalized_type),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT
                    id,
                    course_id,
                    COALESCE(output_type, type) AS output_type,
                    COALESCE(type, output_type) AS type,
                    scope_set_id,
                    scope_artifact_ids,
                    scope,
                    COALESCE(model_used, model) AS model_used,
                    COALESCE(model, model_used) AS model,
                    status,
                    content,
                    path,
                    created_at
                FROM outputs
                WHERE course_id=?
                ORDER BY created_at DESC, id DESC
                """,
                (course_id,),
            ).fetchall()
    return _rows_to_outputs(rows)


def get_output(output_id: int) -> dict[str, Any] | None:
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT
                id,
                course_id,
                COALESCE(output_type, type) AS output_type,
                COALESCE(type, output_type) AS type,
                scope_set_id,
                scope_artifact_ids,
                scope,
                COALESCE(model_used, model) AS model_used,
                COALESCE(model, model_used) AS model,
                status,
                content,
                path,
                created_at
            FROM outputs
            WHERE id=?
            """,
            (int(output_id),),
        ).fetchone()
    items = _rows_to_outputs([row] if row is not None else [])
    return items[0] if items else None


# ---------- Decks / Cards ----------

def create_deck(course_id: str, name: str, deck_type: str) -> int:
    if not course_id:
        raise WorkspaceValidationError("Active course is required before creating a deck.")
    clean_name = (name or "").strip()
    if not clean_name:
        raise WorkspaceValidationError("Deck name is required.")
    normalized_type = (deck_type or "").strip().lower()
    if normalized_type not in VALID_DECK_TYPES:
        raise WorkspaceValidationError("Deck type must be vocab or mcq.")

    now = _now_iso()
    with _connect() as conn:
        cur = conn.execute(
            """
            INSERT INTO decks(course_id, name, deck_type, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (course_id, clean_name, normalized_type, now),
        )
        return int(cur.lastrowid)


def list_decks(course_id: str) -> list[dict[str, Any]]:
    if not course_id:
        return []
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT id, course_id, name, deck_type, created_at
            FROM decks
            WHERE course_id=?
            ORDER BY created_at DESC, id DESC
            """,
            (course_id,),
        ).fetchall()
    return [_row_to_dict(r) or {} for r in rows]


def get_deck(deck_id: int) -> dict[str, Any] | None:
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT id, course_id, name, deck_type, created_at
            FROM decks
            WHERE id=?
            """,
            (int(deck_id),),
        ).fetchone()
    return _row_to_dict(row)


def _delete_cards_for_deck(conn: sqlite3.Connection, deck_id: int) -> None:
    conn.execute("DELETE FROM cards WHERE deck_id=?", (int(deck_id),))


def replace_vocab_cards(deck_id: int, course_id: str, cards: list[dict[str, str]]) -> int:
    now = _now_iso()
    inserted = 0
    with _connect() as conn:
        _delete_cards_for_deck(conn, deck_id)
        for card in cards:
            front = str(card.get("front") or "").strip()
            back = str(card.get("back") or "").strip()
            if not front:
                continue
            conn.execute(
                """
                INSERT INTO cards(deck_id, course_id, card_type, front, back, created_at)
                VALUES (?, ?, 'vocab', ?, ?, ?)
                """,
                (int(deck_id), course_id, front, back, now),
            )
            inserted += 1
    return inserted


def replace_mcq_cards(deck_id: int, course_id: str, questions: list[dict[str, Any]]) -> int:
    now = _now_iso()
    inserted = 0
    with _connect() as conn:
        _delete_cards_for_deck(conn, deck_id)
        for q in questions:
            question = str(q.get("question") or "").strip()
            if not question:
                continue
            options = q.get("options") if isinstance(q.get("options"), list) else []
            conn.execute(
                """
                INSERT INTO cards(
                    deck_id, course_id, card_type, question, options_json, answer, explanation, created_at
                )
                VALUES (?, ?, 'mcq', ?, ?, ?, ?, ?)
                """,
                (
                    int(deck_id),
                    course_id,
                    question,
                    json.dumps(options, ensure_ascii=False),
                    str(q.get("correct_answer") or ""),
                    str(q.get("explanation") or ""),
                    now,
                ),
            )
            inserted += 1
    return inserted


def list_cards(deck_id: int) -> list[dict[str, Any]]:
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT id, deck_id, course_id, card_type, front, back, question, options_json, answer, explanation, created_at
            FROM cards
            WHERE deck_id=?
            ORDER BY id ASC
            """,
            (int(deck_id),),
        ).fetchall()
    out: list[dict[str, Any]] = []
    for row in rows:
        item = _row_to_dict(row) or {}
        raw = item.get("options_json")
        if isinstance(raw, str) and raw.strip():
            try:
                item["options"] = json.loads(raw)
            except json.JSONDecodeError:
                item["options"] = []
        else:
            item["options"] = []
        out.append(item)
    return out
