"""Shared pytest fixtures for UNSWExam test suite."""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

# Ensure src/ is on the path so all service imports resolve.
SRC_DIR = Path(__file__).resolve().parents[1] / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

MIGRATIONS_SQL_DIR = SRC_DIR / "migrations" / "sql"


def _apply_migrations(db_path: str) -> None:
    """Run all SQL migration files in order against *db_path*."""
    conn = sqlite3.connect(db_path)
    try:
        sql_files = sorted(MIGRATIONS_SQL_DIR.glob("[0-9][0-9][0-9]_*.sql"))
        for sql_file in sql_files:
            sql = sql_file.read_text(encoding="utf-8")
            conn.executescript(sql)
        # Set schema_version to latest
        conn.execute(
            "INSERT INTO meta(key, value) VALUES('schema_version', ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (str(len(sql_files)),),
        )
        conn.commit()
    finally:
        conn.close()


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    """Temporary SQLite DB with all migrations applied.

    Monkeypatches DB_PATH in all service modules so tests use an isolated DB.
    """
    db_file = str(tmp_path / "test_app.db")
    _apply_migrations(db_file)

    import migrations.migrate as migrate_mod
    import services.course_workspace_service as cws_mod
    import services.flashcards_mistakes_service as fm_mod
    import utils.metrics as metrics_mod

    monkeypatch.setattr(migrate_mod, "DB_PATH", Path(db_file))
    monkeypatch.setattr(cws_mod, "DB_PATH", Path(db_file))
    monkeypatch.setattr(fm_mod, "DB_PATH", Path(db_file))
    monkeypatch.setattr(metrics_mod, "DB_PATH", Path(db_file))

    # Patch _connect in each module to pick up the new DB_PATH value
    def _patched_connect_cws():
        conn = sqlite3.connect(db_file)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _patched_connect_fm():
        conn = sqlite3.connect(db_file)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _patched_connect_metrics():
        conn = sqlite3.connect(db_file)
        conn.row_factory = sqlite3.Row
        return conn

    monkeypatch.setattr(cws_mod, "_connect", _patched_connect_cws)
    monkeypatch.setattr(fm_mod, "_connect", _patched_connect_fm)
    monkeypatch.setattr(metrics_mod, "_connect", _patched_connect_metrics)

    return db_file
