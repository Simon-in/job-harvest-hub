from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


PlatformName = Literal["boss", "liepin", "zhilian"]


class StartBossRequest(BaseModel):
    keyword: str = Field(..., min_length=1, description="搜索关键词")
    city_code: str = Field(default="101010100", description="城市 code")
    salary: str | None = Field(default=None, description="薪资过滤（平台原始编码）")
    max_pages: int = Field(default=30, ge=1, le=200, description="最大翻页数")
    headless: bool = Field(default=False)
    slow_mo: int = Field(default=50, ge=0, le=2000)
    step_wait_sec: float = Field(default=0.2, ge=0.0, le=5.0, description="统一等待秒数")
    extra_query: list[str] = Field(default_factory=list, description="附加查询参数 KEY=VAL")
    save_raw_json: bool = Field(default=False)


class StartTaskRequest(StartBossRequest):
    platform: PlatformName


class SaveTaskConfigRequest(BaseModel):
    platform: PlatformName
    config: dict[str, Any] = Field(default_factory=dict)


class JobRow(BaseModel):
    id: int
    platform: str
    keyword: str | None = None
    encrypt_id: str | None = None
    job_name: str | None = None
    salary_desc: str | None = None
    location_name: str | None = None
    experience_name: str | None = None
    degree_name: str | None = None
    post_description: str | None = None
    post_requirements: str | None = None
    job_link: str | None = None
    company_name: str | None = None
    boss_name: str | None = None
    boss_title: str | None = None
    raw_json: str | None = None
    created_at: datetime | None = None


class PagedJobsResponse(BaseModel):
    page: int
    size: int
    total: int
    items: list[JobRow]


class TaskStatus(BaseModel):
    platform: str
    running: bool
    last_error: str | None = None
    last_count: int = 0
    last_started_at: datetime | None = None
    last_finished_at: datetime | None = None


class GenericResponse(BaseModel):
    ok: bool
    message: str
    data: dict[str, Any] | None = None
