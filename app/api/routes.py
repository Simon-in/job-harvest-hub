from dataclasses import asdict
import queue
import time

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse

from app.models import GenericResponse, PagedJobsResponse, SaveTaskConfigRequest, StartTaskRequest
from app.repository.config_repo import get_task_config, save_task_config
from app.repository.cookie_repo import clear_platform_cookies, get_cookie_status
from app.repository.jobs_repo import clear_jobs, list_jobs, stats_jobs
from app.services.login_flow_service import run_login_flow
from app.services.platform_options import get_platform_options
from app.services.platform_registry import get_platform_service
from app.services.progress_hub import progress_hub

router = APIRouter(prefix="/api")


@router.get("/health", response_model=GenericResponse)
def health() -> GenericResponse:
    return GenericResponse(ok=True, message="ok")


def _require_service(platform: str):
    service = get_platform_service(platform)
    if service is None:
        raise HTTPException(
            status_code=400,
            detail=f"unsupported platform: {platform}. use boss|liepin|zhilian",
        )
    return service


@router.post("/tasks/start", response_model=GenericResponse)
def start_task(payload: StartTaskRequest) -> GenericResponse:
    service = _require_service(payload.platform)
    task_payload = payload.model_dump()
    platform = task_payload.pop("platform")
    try:
        service.start(task_payload)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return GenericResponse(ok=True, message=f"{platform} task started")


@router.post("/tasks/stop", response_model=GenericResponse)
def stop_task(platform: str = Query(..., description="boss|liepin|zhilian")) -> GenericResponse:
    service = _require_service(platform)
    service.stop()
    return GenericResponse(ok=True, message=f"{platform} stop signal sent")


@router.get("/tasks/status", response_model=GenericResponse)
def task_status(platform: str = Query(..., description="boss|liepin|zhilian")) -> GenericResponse:
    service = _require_service(platform)
    return GenericResponse(ok=True, message="ok", data=asdict(service.status()))


@router.get("/tasks/list", response_model=PagedJobsResponse)
def task_list(
    platform: str = Query(..., description="boss|liepin|zhilian"),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=200),
    keyword: str | None = Query(default=None),
    created_from: str | None = Query(default=None, description="YYYY-MM-DD HH:MM:SS"),
    created_to: str | None = Query(default=None, description="YYYY-MM-DD HH:MM:SS"),
) -> PagedJobsResponse:
    _require_service(platform)
    return list_jobs(
        platform=platform,
        page=page,
        size=size,
        keyword=keyword,
        created_from=created_from,
        created_to=created_to,
    )


@router.get("/tasks/platforms", response_model=GenericResponse)
def task_platforms() -> GenericResponse:
    return GenericResponse(
        ok=True,
        message="ok",
        data={"platforms": ["boss", "liepin", "zhilian"]},
    )


@router.get("/tasks/stats", response_model=GenericResponse)
def task_stats(
    platform: str = Query(..., description="boss|liepin|zhilian"),
    keyword: str | None = Query(default=None),
    created_from: str | None = Query(default=None, description="YYYY-MM-DD HH:MM:SS"),
    created_to: str | None = Query(default=None, description="YYYY-MM-DD HH:MM:SS"),
) -> GenericResponse:
    _require_service(platform)
    return GenericResponse(
        ok=True,
        message="ok",
        data=stats_jobs(
            platform=platform,
            keyword=keyword,
            created_from=created_from,
            created_to=created_to,
        ),
    )


@router.get("/tasks/options", response_model=GenericResponse)
def task_options(platform: str = Query(..., description="boss|liepin|zhilian")) -> GenericResponse:
    _require_service(platform)
    options = get_platform_options(platform)
    return GenericResponse(ok=True, message="ok", data=options or {})


@router.get("/tasks/config", response_model=GenericResponse)
def task_config(platform: str = Query(..., description="boss|liepin|zhilian")) -> GenericResponse:
    _require_service(platform)
    data = get_task_config(platform) or {}
    return GenericResponse(ok=True, message="ok", data=data)


@router.post("/tasks/config", response_model=GenericResponse)
def save_config(payload: SaveTaskConfigRequest) -> GenericResponse:
    _require_service(payload.platform)
    save_task_config(payload.platform, payload.config)
    return GenericResponse(ok=True, message="config saved")


@router.get("/tasks/progress/stream")
def task_progress_stream(
    platform: str = Query(..., description="boss|liepin|zhilian"),
):
    _require_service(platform)

    def gen():
        q = progress_hub.subscribe(platform)
        try:
            yield progress_hub.to_sse({"platform": platform, "message": "connected"}, event="connected")
            while True:
                try:
                    msg = q.get(timeout=1.5)
                    yield progress_hub.to_sse(msg, event="progress")
                except queue.Empty:
                    yield progress_hub.to_sse({"ts": int(time.time())}, event="ping")
        finally:
            progress_hub.unsubscribe(platform, q)

    return StreamingResponse(gen(), media_type="text/event-stream")


@router.post("/tasks/login/start", response_model=GenericResponse)
def task_login_start(
    platform: str = Query(..., description="boss|liepin|zhilian"),
    timeout_sec: int = Query(default=180, ge=30, le=600),
    inject_old_cookie: bool = Query(default=False, description="是否先注入历史Cookie"),
    finish_on_login: bool = Query(default=True, description="检测到已登录后是否提前结束"),
    boss_manual_mode: bool = Query(default=False, description="Boss手动登录模式，禁用自动回拉与自动判定"),
    manual_login_mode: bool = Query(default=False, description="全平台手动模式：仅打开首页，不自动点击登录"),
) -> GenericResponse:
    _require_service(platform)
    result = run_login_flow(
        platform=platform,
        timeout_sec=timeout_sec,
        use_existing_cookies=inject_old_cookie,
        finish_on_login=finish_on_login,
        boss_manual_mode=boss_manual_mode,
        manual_login_mode=manual_login_mode,
    )
    return GenericResponse(ok=True, message="login flow done", data=result)


@router.get("/tasks/login/status", response_model=GenericResponse)
def task_login_status(platform: str = Query(..., description="boss|liepin|zhilian")) -> GenericResponse:
    _require_service(platform)
    return GenericResponse(ok=True, message="ok", data=get_cookie_status(platform))


@router.post("/tasks/login/clear", response_model=GenericResponse)
def task_login_clear(platform: str = Query(..., description="boss|liepin|zhilian")) -> GenericResponse:
    _require_service(platform)
    clear_platform_cookies(platform)
    return GenericResponse(ok=True, message="cookies cleared")


@router.post("/tasks/data/clear", response_model=GenericResponse)
def task_data_clear(
    scope: str = Query(default="all", description="all|platform"),
    platform: str | None = Query(default=None, description="boss|liepin|zhilian"),
) -> GenericResponse:
    scope_l = scope.lower().strip()
    if scope_l not in {"all", "platform"}:
        raise HTTPException(status_code=400, detail="scope must be all|platform")

    target_platform = None
    if scope_l == "platform":
        if not platform:
            raise HTTPException(status_code=400, detail="platform is required when scope=platform")
        _require_service(platform)
        target_platform = platform

    deleted = clear_jobs(target_platform)
    return GenericResponse(
        ok=True,
        message="jobs data cleared",
        data={
            "deleted": deleted,
            "scope": scope_l,
            "platform": target_platform,
        },
    )
