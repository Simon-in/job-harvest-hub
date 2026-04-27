import json
from typing import Any

from app.database import get_conn


def save_task_config(platform: str, config: dict[str, Any]) -> None:
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO task_configs(platform, config_json, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(platform) DO UPDATE SET
                config_json=excluded.config_json,
                updated_at=CURRENT_TIMESTAMP
            """,
            (platform, json.dumps(config, ensure_ascii=False)),
        )


def get_task_config(platform: str) -> dict[str, Any] | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT config_json FROM task_configs WHERE platform = ?",
            (platform,),
        ).fetchone()
    if not row:
        return None
    try:
        return json.loads(row["config_json"])
    except Exception:
        return None
