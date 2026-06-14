from __future__ import annotations

import sqlite3
import os
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

ROOT = Path(__file__).resolve().parents[3]
PROJECT_DB_DIR = ROOT / "data"
PROJECT_DB_FILE = PROJECT_DB_DIR / "resource_tracker_v2.db"


def _load_local_env() -> None:
    for env_file in [ROOT / ".env", ROOT / "apps" / "api" / ".env"]:
        if not env_file.exists():
            continue
        for line in env_file.read_text(encoding="utf-8").splitlines():
            clean = line.strip()
            if not clean or clean.startswith("#") or "=" not in clean:
                continue
            key, value = clean.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_local_env()


def _probe_sqlite_file(db_file: Path) -> Path:
    try:
        db_file.parent.mkdir(parents=True, exist_ok=True)
        if db_file.exists():
            if not os.access(db_file, os.W_OK):
                raise RuntimeError(f"SQLite database file is not writable: {db_file}")
            with sqlite3.connect(f"file:{db_file.as_posix()}?mode=rw", uri=True) as connection:
                connection.execute("PRAGMA user_version")
        else:
            with sqlite3.connect(db_file.as_posix()) as connection:
                connection.execute("CREATE TABLE IF NOT EXISTS __write_probe (id INTEGER PRIMARY KEY)")
                connection.execute("DROP TABLE __write_probe")
                connection.commit()
        return db_file
    except (OSError, sqlite3.Error, RuntimeError) as exc:
        raise RuntimeError(f"SQLite database is not writable: {db_file}") from exc


def _resolve_sqlite_file() -> Path:
    configured = os.getenv("RESOURCE_TRACKER_DB_FILE", "").strip()
    db_file = Path(configured) if configured else PROJECT_DB_FILE
    return _probe_sqlite_file(db_file.resolve())


configured_database_url = os.getenv("DATABASE_URL", "").strip()
if configured_database_url:
    DATABASE_URL = configured_database_url
    DB_FILE: Path | None = None
else:
    DB_FILE = _resolve_sqlite_file()
    DATABASE_URL = f"sqlite:///{DB_FILE.as_posix()}"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {},
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def ensure_runtime_schema() -> None:
    """Add MVP columns to an existing SQLite file without replacing data."""
    if not DATABASE_URL.startswith("sqlite"):
        return
    if DB_FILE is None:
        return
    additions = {
        "articles": [
            ("content_status", "VARCHAR(32) NOT NULL DEFAULT 'missing_content'"),
            ("extraction_status", "VARCHAR(32) NOT NULL DEFAULT 'pending'"),
            ("extraction_version", "VARCHAR(32) NOT NULL DEFAULT ''"),
            ("extraction_message", "TEXT NOT NULL DEFAULT ''"),
        ],
        "resources": [
            ("capability_tags", "JSON NOT NULL DEFAULT '[]'"),
        ],
        "resource_mentions": [
            ("match_keywords", "JSON NOT NULL DEFAULT '[]'"),
        ],
        "source_accounts": [
            ("tracking_status", "VARCHAR(32) NOT NULL DEFAULT 'paused'"),
            ("tracking_source", "VARCHAR(64) NOT NULL DEFAULT 'manual'"),
            ("first_tracked_at", "DATETIME"),
            ("last_analyzed_at", "DATETIME"),
            ("last_checked_at", "DATETIME"),
            ("next_check_at", "DATETIME"),
            ("last_check_status", "VARCHAR(32) NOT NULL DEFAULT ''"),
            ("last_check_message", "TEXT NOT NULL DEFAULT ''"),
            ("consecutive_failures", "INTEGER NOT NULL DEFAULT 0"),
        ],
        "status_checks": [
            ("check_source", "VARCHAR(64) NOT NULL DEFAULT 'initial_ingest'"),
        ],
    }
    with sqlite3.connect(DB_FILE.as_posix()) as connection:
        for table, columns in additions.items():
            existing = {row[1] for row in connection.execute(f"PRAGMA table_info({table})")}
            for name, definition in columns:
                if name not in existing:
                    connection.execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")
        connection.commit()


def get_session():
    with SessionLocal() as session:
        yield session


def create_session() -> Session:
    return SessionLocal()
