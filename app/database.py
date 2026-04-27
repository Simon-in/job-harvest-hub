import sqlite3
from contextlib import contextmanager
from typing import Iterator

from app.config import DB_DIR, DB_PATH


def init_db() -> None:
    DB_DIR.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                platform TEXT NOT NULL,
                keyword TEXT,
                encrypt_id TEXT,
                job_name TEXT,
                salary_desc TEXT,
                location_name TEXT,
                experience_name TEXT,
                degree_name TEXT,
                post_description TEXT,
                post_requirements TEXT,
                job_link TEXT,
                company_name TEXT,
                boss_name TEXT,
                boss_title TEXT,
                raw_json TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_jobs_platform_created ON jobs(platform, created_at DESC)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_jobs_keyword ON jobs(keyword)"
        )
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_jobs_platform_encrypt ON jobs(platform, encrypt_id)"
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS task_configs (
                platform TEXT PRIMARY KEY,
                config_json TEXT NOT NULL,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS task_cookies (
                platform TEXT PRIMARY KEY,
                cookies_json TEXT NOT NULL,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        # Lightweight migration for older local DB files.
        _ensure_job_columns(conn)


def _ensure_job_columns(conn: sqlite3.Connection) -> None:
    exists = {
        row[1]
        for row in conn.execute("PRAGMA table_info(jobs)").fetchall()
    }
    if "post_requirements" not in exists:
        conn.execute("ALTER TABLE jobs ADD COLUMN post_requirements TEXT")
    if "job_link" not in exists:
        conn.execute("ALTER TABLE jobs ADD COLUMN job_link TEXT")


@contextmanager
def get_conn() -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()
