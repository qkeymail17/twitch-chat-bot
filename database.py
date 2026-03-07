import json
import sqlite3
import time
from typing import Optional, List, Dict, Any

from config import DB_PATH, CACHE_TTL_SECONDS


def _connect() -> sqlite3.Connection:
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON;")
    return con


def init_db():
    con = _connect()
    cur = con.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS vod_cache (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        vod_id TEXT NOT NULL,
        fmt TEXT NOT NULL,
        vod_url TEXT NOT NULL,
        title TEXT,
        created_at TEXT,
        channel TEXT,
        length_seconds INTEGER,
        messages INTEGER,
        unique_users INTEGER,
        parts INTEGER,
        html_url TEXT,
        cached_at REAL NOT NULL
    )
    """)

    cur.execute("""
    CREATE UNIQUE INDEX IF NOT EXISTS idx_vod_cache_unique
    ON vod_cache(vod_id, fmt)
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS vod_files (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        cache_id INTEGER NOT NULL,
        part_index INTEGER NOT NULL,
        file_id TEXT NOT NULL,
        file_name TEXT,
        FOREIGN KEY(cache_id) REFERENCES vod_cache(id) ON DELETE CASCADE
    )
    """)

    cur.execute("""
    CREATE INDEX IF NOT EXISTS idx_vod_files_cache_id
    ON vod_files(cache_id)
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS user_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        cache_id INTEGER NOT NULL,
        processed_at REAL NOT NULL,
        FOREIGN KEY(cache_id) REFERENCES vod_cache(id) ON DELETE CASCADE
    )
    """)

    cur.execute("""
    CREATE INDEX IF NOT EXISTS idx_user_history_user_id
    ON user_history(user_id, processed_at)
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS user_settings (
        user_id INTEGER PRIMARY KEY,
        tz_offset_min INTEGER NOT NULL,
        updated_at REAL NOT NULL
    )
    """)

    con.commit()
    con.close()


def upsert_cache(
    vod_id: str,
    fmt: str,
    vod_url: str,
    meta: Dict[str, Any],
    stats: Dict[str, Any],
    files: List[Dict[str, str]],
) -> int:
    con = _connect()
    cur = con.cursor()
    now = time.time()

    html_url = meta.get("html_url")

    cur.execute("""
    INSERT INTO vod_cache(
        vod_id, fmt, vod_url, title, created_at, channel,
        length_seconds, messages, unique_users, parts, html_url, cached_at
    )
    VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
    ON CONFLICT(vod_id, fmt) DO UPDATE SET
      vod_url=excluded.vod_url,
      title=excluded.title,
      created_at=excluded.created_at,
      channel=excluded.channel,
      length_seconds=excluded.length_seconds,
      messages=excluded.messages,
      unique_users=excluded.unique_users,
      parts=excluded.parts,
      html_url=excluded.html_url,
      cached_at=excluded.cached_at
    """, (
        vod_id, fmt, vod_url,
        meta.get("title"), meta.get("created_at"), meta.get("channel"), meta.get("length_seconds"),
        stats.get("messages"), stats.get("unique_users"), stats.get("parts"),
        html_url,
        now
    ))

    cur.execute("SELECT id FROM vod_cache WHERE vod_id=? AND fmt=?", (vod_id, fmt))
    row = cur.fetchone()
    cache_id = int(row["id"])

    cur.execute("DELETE FROM vod_files WHERE cache_id=?", (cache_id,))
    for i, f in enumerate(files, start=1):
        cur.execute("""
        INSERT INTO vod_files(cache_id, part_index, file_id, file_name)
        VALUES(?,?,?,?)
        """, (cache_id, i, f["file_id"], f.get("file_name")))

    con.commit()
    con.close()
    return cache_id


def get_cache(vod_id: str, fmt: str) -> Optional[Dict[str, Any]]:
    con = _connect()
    cur = con.cursor()
    cur.execute("SELECT * FROM vod_cache WHERE vod_id=? AND fmt=?", (vod_id, fmt))
    row = cur.fetchone()
    if not row:
        con.close()
        return None

    cache_id = int(row["id"])
    cur.execute(
        "SELECT part_index, file_id, file_name FROM vod_files WHERE cache_id=? ORDER BY part_index ASC",
        (cache_id,),
    )
    files = [dict(r) for r in cur.fetchall()]

    out = dict(row)
    out["files"] = files
    con.close()
    return out


def cache_is_expired(cache_row: Dict[str, Any]) -> bool:
    cached_at = float(cache_row.get("cached_at") or 0)
    return (time.time() - cached_at) > CACHE_TTL_SECONDS


def add_user_history(user_id: int, cache_id: int):
    con = _connect()
    cur = con.cursor()
    cur.execute("""
    INSERT INTO user_history(user_id, cache_id, processed_at)
    VALUES(?,?,?)
    """, (int(user_id), int(cache_id), time.time()))
    con.commit()
    con.close()


def get_history_for_user(user_id: int, limit: int = 20, offset: int = 0) -> List[Dict[str, Any]]:
    limit = max(1, min(int(limit), 50))
    offset = max(0, int(offset))

    con = _connect()
    cur = con.cursor()

    cur.execute("""
    SELECT cache_id, processed_at
    FROM user_history
    WHERE user_id=?
    ORDER BY processed_at DESC
    LIMIT ? OFFSET ?
    """, (int(user_id), limit, offset))
    rows = cur.fetchall()

    out: List[Dict[str, Any]] = []
    for r in rows:
        cache_id = int(r["cache_id"])
        processed_at = float(r["processed_at"])

        cur.execute("SELECT * FROM vod_cache WHERE id=?", (cache_id,))
        cache = cur.fetchone()
        if not cache:
            continue

        out_item = dict(cache)
        out_item["processed_at"] = processed_at
        out.append(out_item)

    con.close()
    return out


def get_user_tz_offset(user_id: int) -> int:
    con = _connect()
    cur = con.cursor()
    cur.execute("SELECT tz_offset_min FROM user_settings WHERE user_id=?", (int(user_id),))
    row = cur.fetchone()
    con.close()
    if not row:
        return 0
    try:
        return int(row["tz_offset_min"])
    except Exception:
        return 0


def set_user_tz_offset(user_id: int, offset_min: int):
    con = _connect()
    cur = con.cursor()
    cur.execute("""
    INSERT INTO user_settings(user_id, tz_offset_min, updated_at)
    VALUES(?,?,?)
    ON CONFLICT(user_id) DO UPDATE SET
      tz_offset_min=excluded.tz_offset_min,
      updated_at=excluded.updated_at
    """, (int(user_id), int(offset_min), time.time()))
    con.commit()
    con.close()