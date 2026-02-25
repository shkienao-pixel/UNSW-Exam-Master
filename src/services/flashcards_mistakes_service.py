"""Persistence service for v0.2.4 flashcards and mistakes bank."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from typing import Any
from uuid import uuid4

from migrations.migrate import DB_PATH


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _now_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat()


def _json_dumps(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False)


def _json_loads(raw: Any, default: Any) -> Any:
    if raw is None:
        return default
    if isinstance(raw, (dict, list)):
        return raw
    text = str(raw).strip()
    if not text:
        return default
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return default


def _row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {k: row[k] for k in row.keys()}


def _normalize_user_id(user_id: str) -> str:
    clean = str(user_id or "").strip()
    return clean or "default"


def _normalize_course_id(course_id: str) -> str:
    return str(course_id or "").strip()


def _normalize_scope(scope: dict[str, Any] | None) -> dict[str, Any]:
    src = scope if isinstance(scope, dict) else {}
    chapter_ids = src.get("chapterIds") if isinstance(src.get("chapterIds"), list) else []
    file_ids = src.get("fileIds") if isinstance(src.get("fileIds"), list) else []
    norm_file_ids: list[int] = []
    for v in file_ids:
        try:
            norm_file_ids.append(int(v))
        except (TypeError, ValueError):
            continue
    return {"chapterIds": [str(v) for v in chapter_ids], "fileIds": sorted(set(norm_file_ids))}


def _normalize_stats(stats: dict[str, Any] | None = None) -> dict[str, Any]:
    src = stats if isinstance(stats, dict) else {}
    return {
        "seen": int(src.get("seen") or 0),
        "known": int(src.get("known") or 0),
        "unknown": int(src.get("unknown") or 0),
        "lastReviewedAt": src.get("lastReviewedAt"),
    }


def _normalize_answer_from_options(options: list[str], raw_answer: Any) -> str:
    if not options:
        return str(raw_answer or "").strip()
    answer_text = str(raw_answer or "").strip()
    if answer_text in options:
        return answer_text
    try:
        parsed = int(answer_text)
    except (TypeError, ValueError):
        parsed = None
    if parsed is not None:
        if 0 <= parsed < len(options):
            return options[parsed]
        if 1 <= parsed <= len(options):
            return options[parsed - 1]
    letter = answer_text[:1].upper()
    if letter in {"A", "B", "C", "D"}:
        idx = ord(letter) - ord("A")
        if 0 <= idx < len(options):
            return options[idx]
    return options[0]


def save_generated_flashcards(
    user_id: str,
    course_id: str,
    deck_id: str,
    cards: list[dict[str, Any]],
    scope: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    normalized_user_id = _normalize_user_id(user_id)
    normalized_course_id = _normalize_course_id(course_id)
    normalized_scope = _normalize_scope(scope)
    now = _now_iso()
    out: list[dict[str, Any]] = []
    with _connect() as conn:
        for card in cards:
            card_type = str(card.get("type") or "").strip().lower()
            if card_type not in {"mcq", "knowledge"}:
                continue
            front = card.get("front") if isinstance(card.get("front"), dict) else {}
            back = card.get("back") if isinstance(card.get("back"), dict) else {}
            source_refs = card.get("sourceRefs") if isinstance(card.get("sourceRefs"), list) else []
            card_id = str(card.get("id") or uuid4())
            stats = _normalize_stats(card.get("stats") if isinstance(card.get("stats"), dict) else None)
            conn.execute(
                """
                INSERT INTO flashcards(
                    id, user_id, course_id, deck_id, card_type,
                    scope_json, front_json, back_json, stats_json, source_refs_json,
                    created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    card_id,
                    normalized_user_id,
                    normalized_course_id,
                    str(deck_id),
                    card_type,
                    _json_dumps(normalized_scope),
                    _json_dumps(front),
                    _json_dumps(back),
                    _json_dumps(stats),
                    _json_dumps(source_refs),
                    now,
                    now,
                ),
            )
            out.append(
                {
                    "id": card_id,
                    "userId": normalized_user_id,
                    "courseId": normalized_course_id,
                    "deckId": str(deck_id),
                    "type": card_type,
                    "scope": normalized_scope,
                    "front": front,
                    "back": back,
                    "stats": stats,
                    "sourceRefs": source_refs,
                    "createdAt": now,
                    "updatedAt": now,
                }
            )
    return out


def get_flashcard(card_id: str, user_id: str = "") -> dict[str, Any] | None:
    cid = str(card_id or "").strip()
    if not cid:
        return None
    normalized_user_id = _normalize_user_id(user_id) if user_id else ""
    with _connect() as conn:
        if normalized_user_id:
            row = conn.execute(
                """
                SELECT *
                FROM flashcards
                WHERE id=? AND user_id=?
                """,
                (cid, normalized_user_id),
            ).fetchone()
        else:
            row = conn.execute(
                """
                SELECT *
                FROM flashcards
                WHERE id=?
                """,
                (cid,),
            ).fetchone()
    item = _row_to_dict(row)
    if not item:
        return None
    return {
        "id": item["id"],
        "userId": item["user_id"],
        "courseId": item["course_id"],
        "deckId": item["deck_id"],
        "type": item["card_type"],
        "scope": _json_loads(item.get("scope_json"), {"chapterIds": [], "fileIds": []}),
        "front": _json_loads(item.get("front_json"), {}),
        "back": _json_loads(item.get("back_json"), {}),
        "stats": _normalize_stats(_json_loads(item.get("stats_json"), {})),
        "sourceRefs": _json_loads(item.get("source_refs_json"), []),
        "createdAt": item["created_at"],
        "updatedAt": item["updated_at"],
    }


def list_flashcards_by_deck(user_id: str, deck_id: str) -> list[dict[str, Any]]:
    normalized_user_id = _normalize_user_id(user_id)
    d_id = str(deck_id or "").strip()
    if not d_id:
        return []
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT id, user_id, course_id, deck_id, card_type,
                   scope_json, front_json, back_json, stats_json, source_refs_json,
                   created_at, updated_at
            FROM flashcards
            WHERE user_id=? AND deck_id=?
            ORDER BY created_at ASC, id ASC
            """,
            (normalized_user_id, d_id),
        ).fetchall()
    out: list[dict[str, Any]] = []
    for row in rows:
        item = _row_to_dict(row)
        if not item:
            continue
        out.append({
            "id": item["id"],
            "userId": item["user_id"],
            "courseId": item["course_id"],
            "deckId": item["deck_id"],
            "type": item["card_type"],
            "scope": _json_loads(item.get("scope_json"), {"chapterIds": [], "fileIds": []}),
            "front": _json_loads(item.get("front_json"), {}),
            "back": _json_loads(item.get("back_json"), {}),
            "stats": _normalize_stats(_json_loads(item.get("stats_json"), {})),
            "sourceRefs": _json_loads(item.get("source_refs_json"), []),
            "createdAt": item["created_at"],
            "updatedAt": item["updated_at"],
        })
    return out


def upsert_mistake(user_id: str, flashcard_id: str) -> dict[str, Any]:
    normalized_user_id = _normalize_user_id(user_id)
    card_id = str(flashcard_id or "").strip()
    if not card_id:
        raise ValueError("flashcard_id is required")
    now = _now_iso()
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO mistakes(
                user_id, flashcard_id, status, added_at, wrong_count, last_wrong_at, updated_at
            )
            VALUES (?, ?, 'active', ?, 1, ?, ?)
            ON CONFLICT(user_id, flashcard_id)
            DO UPDATE SET
                status='active',
                wrong_count=mistakes.wrong_count + 1,
                last_wrong_at=excluded.last_wrong_at,
                updated_at=excluded.updated_at
            """,
            (normalized_user_id, card_id, now, now, now),
        )
        row = conn.execute(
            """
            SELECT id, user_id, flashcard_id, status, added_at, wrong_count, last_wrong_at, updated_at
            FROM mistakes
            WHERE user_id=? AND flashcard_id=?
            """,
            (normalized_user_id, card_id),
        ).fetchone()
    item = _row_to_dict(row) or {}
    return {
        "id": int(item.get("id", 0)),
        "userId": item.get("user_id", normalized_user_id),
        "flashcardId": item.get("flashcard_id", card_id),
        "status": item.get("status", "active"),
        "addedAt": item.get("added_at"),
        "wrongCount": int(item.get("wrong_count", 1)),
        "lastWrongAt": item.get("last_wrong_at"),
        "updatedAt": item.get("updated_at"),
    }


def review_flashcard(user_id: str, card_id: str, action: str) -> dict[str, Any]:
    normalized_user_id = _normalize_user_id(user_id)
    card = get_flashcard(card_id, normalized_user_id)
    if not card:
        raise ValueError("flashcard not found")
    normalized_action = str(action or "").strip().lower()
    if normalized_action not in {"known", "unknown"}:
        raise ValueError("action must be known or unknown")

    stats = _normalize_stats(card.get("stats") if isinstance(card.get("stats"), dict) else None)
    stats["seen"] = int(stats.get("seen") or 0) + 1
    if normalized_action == "known":
        stats["known"] = int(stats.get("known") or 0) + 1
    else:
        stats["unknown"] = int(stats.get("unknown") or 0) + 1
    now = _now_iso()
    stats["lastReviewedAt"] = now

    with _connect() as conn:
        conn.execute(
            "UPDATE flashcards SET stats_json=?, updated_at=? WHERE id=? AND user_id=?",
            (_json_dumps(stats), now, str(card_id), normalized_user_id),
        )

    mistake = upsert_mistake(normalized_user_id, str(card_id)) if normalized_action == "unknown" else None
    updated = get_flashcard(str(card_id), normalized_user_id)
    if not updated:
        raise ValueError("flashcard update failed")
    return {"flashcard": updated, "mistake": mistake}


def submit_flashcard_answer(user_id: str, card_id: str, selected_option: Any) -> dict[str, Any]:
    normalized_user_id = _normalize_user_id(user_id)
    card = get_flashcard(card_id, normalized_user_id)
    if not card:
        raise ValueError("flashcard not found")
    card_type = str(card.get("type") or "").strip().lower()
    if card_type != "mcq":
        raise ValueError("submit is only available for mcq cards")

    front = card.get("front") if isinstance(card.get("front"), dict) else {}
    back = card.get("back") if isinstance(card.get("back"), dict) else {}
    options = [str(x) for x in (front.get("options") or []) if str(x).strip()]
    if not options:
        options = ["A", "B", "C", "D"]

    selected = _normalize_answer_from_options(options, selected_option)
    correct = _normalize_answer_from_options(options, back.get("answer"))
    is_correct = selected == correct

    stats = _normalize_stats(card.get("stats") if isinstance(card.get("stats"), dict) else None)
    stats["seen"] = int(stats.get("seen") or 0) + 1
    if is_correct:
        stats["known"] = int(stats.get("known") or 0) + 1
    else:
        stats["unknown"] = int(stats.get("unknown") or 0) + 1
    now = _now_iso()
    stats["lastReviewedAt"] = now

    with _connect() as conn:
        conn.execute(
            "UPDATE flashcards SET stats_json=?, updated_at=? WHERE id=? AND user_id=?",
            (_json_dumps(stats), now, str(card_id), normalized_user_id),
        )

    mistake = None if is_correct else upsert_mistake(normalized_user_id, str(card_id))
    updated = get_flashcard(str(card_id), normalized_user_id)
    if not updated:
        raise ValueError("flashcard update failed")
    return {
        "flashcard": updated,
        "selectedOption": selected,
        "correctAnswer": correct,
        "isCorrect": bool(is_correct),
        "mistake": mistake,
    }


def list_mistakes(user_id: str, status: str = "", card_type: str = "") -> list[dict[str, Any]]:
    normalized_user_id = _normalize_user_id(user_id)
    status_filter = str(status or "").strip().lower()
    type_filter = str(card_type or "").strip().lower()
    params: list[Any] = [normalized_user_id]
    where = ["m.user_id=?"]
    if status_filter:
        where.append("m.status=?")
        params.append(status_filter)
    if type_filter:
        where.append("f.card_type=?")
        params.append(type_filter)
    with _connect() as conn:
        rows = conn.execute(
            f"""
            SELECT
                m.id,
                m.user_id,
                m.flashcard_id,
                m.status,
                m.added_at,
                m.wrong_count,
                m.last_wrong_at,
                m.updated_at,
                f.card_type,
                f.front_json,
                f.back_json,
                f.scope_json,
                f.source_refs_json
            FROM mistakes m
            JOIN flashcards f ON f.id=m.flashcard_id
            WHERE {' AND '.join(where)}
            ORDER BY m.wrong_count DESC, m.last_wrong_at DESC, m.id DESC
            """,
            tuple(params),
        ).fetchall()
    out: list[dict[str, Any]] = []
    for row in rows:
        item = _row_to_dict(row) or {}
        out.append(
            {
                "id": int(item.get("id", 0)),
                "userId": item.get("user_id", normalized_user_id),
                "flashcardId": item.get("flashcard_id"),
                "status": item.get("status", "active"),
                "addedAt": item.get("added_at"),
                "wrongCount": int(item.get("wrong_count", 0)),
                "lastWrongAt": item.get("last_wrong_at"),
                "updatedAt": item.get("updated_at"),
                "cardType": item.get("card_type"),
                "front": _json_loads(item.get("front_json"), {}),
                "back": _json_loads(item.get("back_json"), {}),
                "scope": _json_loads(item.get("scope_json"), {"chapterIds": [], "fileIds": []}),
                "sourceRefs": _json_loads(item.get("source_refs_json"), []),
            }
        )
    return out


def list_mistakes_review(user_id: str, card_type: str = "") -> list[dict[str, Any]]:
    return list_mistakes(user_id=user_id, status="active", card_type=card_type)


def mark_mistake_master(user_id: str, mistake_id: int) -> bool:
    normalized_user_id = _normalize_user_id(user_id)
    now = _now_iso()
    with _connect() as conn:
        cur = conn.execute(
            "UPDATE mistakes SET status='mastered', updated_at=? WHERE id=? AND user_id=?",
            (now, int(mistake_id), normalized_user_id),
        )
    return int(cur.rowcount or 0) > 0


def archive_mistake(user_id: str, mistake_id: int) -> bool:
    normalized_user_id = _normalize_user_id(user_id)
    now = _now_iso()
    with _connect() as conn:
        cur = conn.execute(
            "UPDATE mistakes SET status='archived', updated_at=? WHERE id=? AND user_id=?",
            (now, int(mistake_id), normalized_user_id),
        )
    return int(cur.rowcount or 0) > 0
