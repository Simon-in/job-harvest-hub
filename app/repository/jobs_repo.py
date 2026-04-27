import json
from typing import Any

from app.database import get_conn
from app.models import JobRow, PagedJobsResponse


def _build_where(
    *,
    platform: str,
    keyword: str | None = None,
    created_from: str | None = None,
    created_to: str | None = None,
) -> tuple[str, list[Any]]:
    where = "WHERE platform = ?"
    params: list[Any] = [platform]
    if keyword:
        where += " AND (keyword LIKE ? OR job_name LIKE ? OR company_name LIKE ?)"
        fuzzy = f"%{keyword}%"
        params.extend([fuzzy, fuzzy, fuzzy])
    if created_from:
        where += " AND created_at >= ?"
        params.append(created_from.strip())
    if created_to:
        where += " AND created_at <= ?"
        params.append(created_to.strip())
    return where, params


def insert_job(job: dict[str, Any]) -> bool:
    with get_conn() as conn:
        cur = conn.execute(
            """
            INSERT OR IGNORE INTO jobs (
                platform, keyword, encrypt_id, job_name, salary_desc, location_name,
                experience_name, degree_name, post_description, post_requirements, job_link,
                company_name,
                boss_name, boss_title, raw_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                job.get("platform"),
                job.get("keyword"),
                job.get("encrypt_id"),
                job.get("job_name"),
                job.get("salary_desc"),
                job.get("location_name"),
                job.get("experience_name"),
                job.get("degree_name"),
                job.get("post_description"),
                job.get("post_requirements"),
                job.get("job_link"),
                job.get("company_name"),
                job.get("boss_name"),
                job.get("boss_title"),
                json.dumps(job.get("raw_json"), ensure_ascii=False) if job.get("raw_json") is not None else None,
            ),
        )
        return cur.rowcount > 0


def list_jobs(
    platform: str,
    page: int,
    size: int,
    keyword: str | None = None,
    created_from: str | None = None,
    created_to: str | None = None,
) -> PagedJobsResponse:
    offset = (page - 1) * size
    where, params = _build_where(
        platform=platform,
        keyword=keyword,
        created_from=created_from,
        created_to=created_to,
    )

    with get_conn() as conn:
        total = conn.execute(f"SELECT COUNT(1) FROM jobs {where}", params).fetchone()[0]
        rows = conn.execute(
            f"""
            SELECT id, platform, keyword, encrypt_id, job_name, salary_desc, location_name,
                   experience_name, degree_name, post_description, post_requirements, job_link,
                   company_name, boss_name,
                   boss_title, raw_json, created_at
            FROM jobs
            {where}
            ORDER BY id DESC
            LIMIT ? OFFSET ?
            """,
            [*params, size, offset],
        ).fetchall()

    items = [JobRow(**dict(row)) for row in rows]
    return PagedJobsResponse(page=page, size=size, total=total, items=items)


def stats_jobs(
    platform: str,
    keyword: str | None = None,
    created_from: str | None = None,
    created_to: str | None = None,
) -> dict[str, Any]:
    where, params = _build_where(
        platform=platform,
        keyword=keyword,
        created_from=created_from,
        created_to=created_to,
    )

    with get_conn() as conn:
        total = conn.execute(f"SELECT COUNT(1) FROM jobs {where}", params).fetchone()[0]
        uniq_companies = conn.execute(
            f"SELECT COUNT(DISTINCT company_name) FROM jobs {where}", params
        ).fetchone()[0]
        top_companies_rows = conn.execute(
            f"""
            SELECT company_name, COUNT(1) AS cnt
            FROM jobs
            {where}
            AND company_name IS NOT NULL
            AND company_name <> ''
            GROUP BY company_name
            ORDER BY cnt DESC
            LIMIT 10
            """,
            params,
        ).fetchall()
        top_locations_rows = conn.execute(
            f"""
            SELECT location_name, COUNT(1) AS cnt
            FROM jobs
            {where}
            AND location_name IS NOT NULL
            AND location_name <> ''
            GROUP BY location_name
            ORDER BY cnt DESC
            LIMIT 10
            """,
            params,
        ).fetchall()
        top_experience_rows = conn.execute(
            f"""
            SELECT experience_name, COUNT(1) AS cnt
            FROM jobs
            {where}
            AND experience_name IS NOT NULL
            AND experience_name <> ''
            GROUP BY experience_name
            ORDER BY cnt DESC
            LIMIT 10
            """,
            params,
        ).fetchall()
        top_degree_rows = conn.execute(
            f"""
            SELECT degree_name, COUNT(1) AS cnt
            FROM jobs
            {where}
            AND degree_name IS NOT NULL
            AND degree_name <> ''
            GROUP BY degree_name
            ORDER BY cnt DESC
            LIMIT 10
            """,
            params,
        ).fetchall()

    return {
        "total": int(total or 0),
        "unique_companies": int(uniq_companies or 0),
        "top_companies": [dict(r) for r in top_companies_rows],
        "top_locations": [dict(r) for r in top_locations_rows],
        "top_experience": [dict(r) for r in top_experience_rows],
        "top_degree": [dict(r) for r in top_degree_rows],
    }


def clear_jobs(platform: str | None = None) -> int:
    with get_conn() as conn:
        if platform:
            cur = conn.execute("DELETE FROM jobs WHERE platform = ?", (platform,))
        else:
            cur = conn.execute("DELETE FROM jobs")
        return int(cur.rowcount or 0)
