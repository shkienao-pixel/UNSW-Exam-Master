"""Lightweight operation metrics logger backed by SQLite."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any

# Resolved at module load time; tests can monkeypatch this symbol.
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
DB_PATH: Path = _PROJECT_ROOT / "data" / "app.db"


def _now_iso() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat()


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def log_metric(operation: str, elapsed_s: float, course_id: str = "", **meta: Any) -> None:
    """Persist a single operation metric row.

    Never raises — metric failures must not interrupt the main user flow.

    Args:
        operation: e.g. "index", "summary", "quiz", "flashcard", "graph", "chat"
        elapsed_s: Wall-clock seconds the operation took.
        course_id: Optional course identifier for filtering.
        **meta:  Arbitrary key-value pairs stored as JSON (e.g. chunks_added=42).
    """
    try:
        meta_json = json.dumps(meta, ensure_ascii=False, default=str)
        with _connect() as conn:
            conn.execute(
                """
                INSERT INTO operation_metrics (operation, course_id, elapsed_s, meta_json, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (operation, course_id or "", round(elapsed_s, 3), meta_json, _now_iso()),
            )
    except Exception:  # noqa: BLE001
        pass


def get_recent_metrics(limit: int = 50) -> list[dict[str, Any]]:
    """Return the most recent *limit* metric rows, newest first.

    Returns an empty list on any error (e.g. table not yet created).
    """
    try:
        with _connect() as conn:
            rows = conn.execute(
                """
                SELECT id, operation, course_id, elapsed_s, meta_json, created_at
                FROM operation_metrics
                ORDER BY id DESC
                LIMIT ?
                """,
                (max(1, limit),),
            ).fetchall()
        out: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            try:
                item["meta"] = json.loads(item.pop("meta_json") or "{}")
            except Exception:  # noqa: BLE001
                item["meta"] = {}
            out.append(item)
        return out
    except Exception:  # noqa: BLE001
        return []


def get_metrics_summary() -> dict[str, Any]:
    """Return per-operation averages and total counts for the Dashboard.

    Returns empty dict on any error.
    """
    try:
        with _connect() as conn:
            rows = conn.execute(
                """
                SELECT
                    operation,
                    COUNT(*)          AS total,
                    AVG(elapsed_s)    AS avg_s,
                    MIN(elapsed_s)    AS min_s,
                    MAX(elapsed_s)    AS max_s,
                    MAX(created_at)   AS last_at
                FROM operation_metrics
                GROUP BY operation
                ORDER BY total DESC
                """
            ).fetchall()
        return {
            row["operation"]: {
                "total": row["total"],
                "avg_s": round(row["avg_s"], 2),
                "min_s": round(row["min_s"], 2),
                "max_s": round(row["max_s"], 2),
                "last_at": row["last_at"],
            }
            for row in rows
        }
    except Exception:  # noqa: BLE001
        return {}
