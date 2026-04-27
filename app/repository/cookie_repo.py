import json
import time
from typing import Any

from app.database import get_conn


def save_platform_cookies(platform: str, cookies: list[dict[str, Any]]) -> None:
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO task_cookies(platform, cookies_json, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(platform) DO UPDATE SET
                cookies_json=excluded.cookies_json,
                updated_at=CURRENT_TIMESTAMP
            """,
            (platform, json.dumps(cookies, ensure_ascii=False)),
        )


def get_platform_cookies(platform: str) -> list[dict[str, Any]]:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT cookies_json FROM task_cookies WHERE platform = ?",
            (platform,),
        ).fetchone()
    if not row:
        return []
    try:
        obj = json.loads(row["cookies_json"])
        return obj if isinstance(obj, list) else []
    except Exception:
        return []


def clear_platform_cookies(platform: str) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM task_cookies WHERE platform = ?", (platform,))


def get_cookie_status(platform: str) -> dict[str, Any]:
    now = int(time.time())
    cookies = get_platform_cookies(platform)
    total = len(cookies)
    active = 0
    for c in cookies:
        exp = c.get("expires")
        if exp is None or exp in (-1, 0):
            active += 1
            continue
        try:
            if int(exp) > now:
                active += 1
        except Exception:
            active += 1

    with get_conn() as conn:
        row = conn.execute(
            "SELECT updated_at FROM task_cookies WHERE platform = ?",
            (platform,),
        ).fetchone()
    updated_at = row["updated_at"] if row else None
    return {
        "platform": platform,
        "has_cookies": total > 0,
        "total_count": total,
        "active_count": active,
        "updated_at": updated_at,
    }
