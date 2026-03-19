import time
from typing import List, Dict, Any

from .db_core import _connect


def add_user_history(user_id: int, cache_id: int):
    con = _connect()
    cur = con.cursor()

    # получаем параметры результата
    cur.execute("SELECT vod_id, fmt FROM vod_cache WHERE id=?", (int(cache_id),))
    row = cur.fetchone()
    if not row:
        con.close()
        return

    vod_id = row["vod_id"]
    fmt = row["fmt"]

    # проверяем, есть ли уже такая запись у пользователя
    cur.execute("""
    SELECT 1
    FROM user_history uh
    JOIN vod_cache vc ON vc.id = uh.cache_id
    WHERE uh.user_id = ?
      AND vc.vod_id = ?
      AND vc.fmt = ?
    LIMIT 1
    """, (int(user_id), vod_id, fmt))

    exists = cur.fetchone()

    if not exists:
        cur.execute("""
        INSERT INTO user_history(user_id, cache_id, processed_at)
        VALUES(?,?,?)
        """, (int(user_id), int(cache_id), time.time()))
        con.commit()

    con.close()


def get_history_for_user(user_id: int, limit: int = 10, offset: int = 0) -> List[Dict[str, Any]]:
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