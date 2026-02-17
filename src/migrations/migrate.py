"""SQLite schema migration runner with backups."""

from __future__ import annotations

import re
import shutil
import sqlite3
import zipfile
from datetime import datetime
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
DB_PATH = DATA_DIR / "app.db"
BACKUPS_DIR = PROJECT_ROOT / "backups"
LOCK_PATH = BACKUPS_DIR / ".migrate.lock"
MIGRATIONS_SQL_DIR = Path(__file__).resolve().parent / "sql"


def _ensure_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    BACKUPS_DIR.mkdir(parents=True, exist_ok=True)


class MigrationError(RuntimeError):
    """Raised when a migration fails and rollback was triggered."""


class MigrationInProgressError(RuntimeError):
    """Raised when a migration lock already exists."""


def _list_migrations() -> list[tuple[int, Path]]:
    files = sorted(MIGRATIONS_SQL_DIR.glob("[0-9][0-9][0-9]_*.sql"))
    out: list[tuple[int, Path]] = []
    for path in files:
        match = re.match(r"^(\d{3})_", path.name)
        if not match:
            continue
        out.append((int(match.group(1)), path))
    out.sort(key=lambda x: x[0])
    return out


def latest_migration_version() -> int:
    """Return the latest migration numeric version from sql files."""
    migrations = _list_migrations()
    return migrations[-1][0] if migrations else 0


def _read_schema_version(conn: sqlite3.Connection) -> int:
    cur = conn.cursor()
    # Backward compatible: if meta table does not exist yet, version is 0.
    cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='meta'")
    if cur.fetchone() is None:
        return 0
    cur.execute("SELECT value FROM meta WHERE key = 'schema_version'")
    row = cur.fetchone()
    if not row:
        return 0
    try:
        return int(row[0])
    except (TypeError, ValueError):
        return 0


def _set_schema_version(conn: sqlite3.Connection, version: int) -> None:
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO meta(key, value)
        VALUES('schema_version', ?)
        ON CONFLICT(key) DO UPDATE SET value=excluded.value
        """,
        (str(version),),
    )


def _backup_if_needed(db_existed_before: bool) -> None:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    if db_existed_before and DB_PATH.exists():
        shutil.copy2(DB_PATH, BACKUPS_DIR / f"app_{timestamp}.db")

    subjects_dir = DATA_DIR / "subjects"
    if subjects_dir.exists() and subjects_dir.is_dir():
        zip_path = BACKUPS_DIR / f"subjects_{timestamp}.zip"
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for p in subjects_dir.rglob("*"):
                if p.is_file():
                    zf.write(p, arcname=str(p.relative_to(subjects_dir)))


def _acquire_lock() -> None:
    try:
        LOCK_PATH.touch(exist_ok=False)
    except FileExistsError as e:
        raise MigrationInProgressError("migration in progress") from e


def _release_lock() -> None:
    if LOCK_PATH.exists():
        try:
            LOCK_PATH.unlink()
        except OSError:
            pass


def migrate_to_latest() -> int:
    """
    Run pending SQL migrations and return the final schema version.

    Backward compatible:
    - If DB does not exist, it is created.
    - If meta table/version is missing, current version defaults to 0.
    """
    _ensure_dirs()
    _acquire_lock()
    migrations = _list_migrations()
    if not migrations:
        _release_lock()
        return 0

    db_existed_before = DB_PATH.exists()
    conn = sqlite3.connect(DB_PATH)
    try:
        current = _read_schema_version(conn)
        pending = [(v, p) for v, p in migrations if v > current]
        if not pending:
            return current

        _backup_if_needed(db_existed_before=db_existed_before)
        for version, sql_path in pending:
            sql = sql_path.read_text(encoding="utf-8")
            try:
                conn.execute("BEGIN IMMEDIATE")
                conn.executescript(sql)
                _set_schema_version(conn, version)
                conn.commit()
            except Exception as e:
                conn.rollback()
                raise MigrationError(
                    f"Migration failed at {sql_path.name}. Rolled back. "
                    f"Use backups in: {BACKUPS_DIR}"
                ) from e
        return pending[-1][0]
    finally:
        conn.close()
        _release_lock()
