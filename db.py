"""SQLite helpers for tracking upload history."""
import sqlite3
import os
from datetime import date

DB_PATH = os.environ.get("DB_PATH", "upload_history.db")


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS uploads (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                source_filename TEXT UNIQUE,
                youtube_id    TEXT,
                youtube_title TEXT,
                uploaded_at   TEXT,
                status        TEXT
            )
        """)
        conn.commit()


def already_uploaded(source_filename: str) -> bool:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT id FROM uploads WHERE source_filename = ? AND status = 'success'",
            (source_filename,)
        ).fetchone()
    return row is not None


def record_upload(source_filename: str, youtube_id: str, youtube_title: str, status: str):
    from datetime import datetime
    ts = datetime.utcnow().isoformat()
    with get_conn() as conn:
        conn.execute("""
            INSERT INTO uploads (source_filename, youtube_id, youtube_title, uploaded_at, status)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(source_filename) DO UPDATE SET
                youtube_id = excluded.youtube_id,
                youtube_title = excluded.youtube_title,
                uploaded_at = excluded.uploaded_at,
                status = excluded.status
        """, (source_filename, youtube_id, youtube_title, ts, status))
        conn.commit()


def get_recent_uploads(n: int = 50):
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM uploads ORDER BY uploaded_at DESC LIMIT ?", (n,)
        ).fetchall()
    return [dict(r) for r in rows]


def get_daily_count(today: str = None) -> int:
    if today is None:
        today = date.today().isoformat()
    with get_conn() as conn:
        row = conn.execute(
            "SELECT COUNT(*) as cnt FROM uploads WHERE status='success' AND DATE(uploaded_at) = ?",
            (today,)
        ).fetchone()
    return row["cnt"] if row else 0
