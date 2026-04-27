import json
import re
import threading
import time
import urllib.parse
from datetime import datetime
from typing import Any

from playwright.sync_api import Page, Response, sync_playwright

from app.repository.cookie_repo import get_platform_cookies, save_platform_cookies
from app.repository.jobs_repo import insert_job
from app.services.job_platform_service import JobPlatformService

LIEPIN_BASE_URL = "https://www.liepin.com/zhaopin/"
JOB_CARDS_SELECTOR = "div[class*='job-card-pc-container']"
NEXT_PAGE_SELECTOR = "li.ant-pagination-next"
SEARCH_API_KEY = "com.liepin.searchfront4c.pc-search-job"
SEARCH_API_INIT_KEY = "com.liepin.searchfront4c.pc-search-job-cond-init"


class LiepinPlatformService(JobPlatformService):
    def __init__(self):
        super().__init__(platform="liepin")
        self._thread: threading.Thread | None = None

    def start(self, payload: dict[str, Any]) -> None:
        if self.state.running:
            raise RuntimeError("Liepin task is already running")
        self.stop_event.clear()
        self.state.running = True
        self.state.last_error = None
        self.state.last_count = 0
        self.state.last_started_at = datetime.now()
        self.emit_progress("任务已启动")
        self._thread = threading.Thread(target=self._run, args=(payload,), daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self.stop_event.set()
        self.emit_progress("收到停止指令")

    def _run(self, payload: dict[str, Any]) -> None:
        try:
            self.state.last_count = self._collect(payload)
            self.emit_progress(f"任务完成，新增 {self.state.last_count} 条")
        except Exception as exc:  # pragma: no cover
            self.state.last_error = str(exc)
            self.emit_progress(f"任务异常：{exc}")
        finally:
            self.state.running = False
            self.state.last_finished_at = datetime.now()

    def _collect(self, payload: dict[str, Any]) -> int:
        keyword = str(payload["keyword"]).strip()
        city_code = str(payload.get("city_code", "")).strip()
        salary = str(payload.get("salary", "")).strip()
        max_pages = int(payload.get("max_pages", 30))
        headless = bool(payload.get("headless", False))
        slow_mo = int(payload.get("slow_mo", 50))
        step_wait_sec = float(payload.get("step_wait_sec", max(slow_mo, 0) / 1000))
        save_raw = bool(payload.get("save_raw_json", False))
        extra_query = [x for x in payload.get("extra_query", []) if isinstance(x, str) and "=" in x]

        params = []
        if city_code:
            params.extend([f"city={urllib.parse.quote(city_code, safe='')}", f"dq={urllib.parse.quote(city_code, safe='')}"])
        if salary:
            params.append(f"salary={urllib.parse.quote(salary, safe='')}")
        params.extend(extra_query)
        params.append("currentPage=0")
        params.append(f"key={urllib.parse.quote(keyword, safe='')}")
        url = f"{LIEPIN_BASE_URL}?{'&'.join(params)}"
        self.emit_progress(f"开始采集关键词：{keyword}")

        inserted = 0
        seen: set[str] = set()

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=headless, slow_mo=slow_mo)
            context = browser.new_context(
                viewport={"width": 1920, "height": 1080},
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
                ),
            )
            saved_cookies = get_platform_cookies(self.platform)
            if saved_cookies:
                try:
                    context.add_cookies(saved_cookies)
                    self.emit_progress(f"已复用Cookie: {len(saved_cookies)}条")
                except Exception:
                    self.emit_progress("历史Cookie注入失败，将继续尝试无Cookie采集")
            page = context.new_page()

            def on_response(resp: Response) -> None:
                nonlocal inserted
                if self.stop_event.is_set():
                    return
                u = resp.url or ""
                if SEARCH_API_KEY not in u or SEARCH_API_INIT_KEY in u:
                    return
                try:
                    content_type = resp.header_value("content-type") or ""
                    if "application/json" not in content_type and "text/json" not in content_type:
                        return
                    rows = self._parse_search_json(resp.text(), keyword=keyword, save_raw=save_raw)
                    for row in rows:
                        eid = row.get("encrypt_id")
                        if isinstance(eid, str) and eid:
                            if eid in seen:
                                continue
                            seen.add(eid)
                        if insert_job(row):
                            inserted += 1
                            if inserted % 10 == 0:
                                self.emit_progress(f"已采集 {inserted} 条")
                except Exception:
                    return

            page.on("response", on_response)
            page.goto(url, wait_until="domcontentloaded", timeout=60_000)

            self._submit_keyword_search(page, keyword)
            self._wait_keyword_results(page, keyword, timeout_ms=20_000)

            self._wait_job_cards(page, timeout_ms=20_000)
            self._pause(step_wait_sec)

            for _ in range(max_pages - 1):
                if self.stop_event.is_set():
                    self.emit_progress("采集中止")
                    break
                next_btn = page.locator(NEXT_PAGE_SELECTOR)
                if next_btn.count() == 0:
                    break
                cls = (next_btn.first.get_attribute("class") or "").lower()
                if "disabled" in cls:
                    break
                try:
                    with page.expect_response(
                        lambda r: bool((r.url or "").find(SEARCH_API_KEY) >= 0 and SEARCH_API_INIT_KEY not in (r.url or "")),
                        timeout=20_000,
                    ):
                        next_btn.first.click()
                except Exception:
                    break
                self._pause(step_wait_sec)
                self.emit_progress("翻页采集中")

            try:
                save_platform_cookies(self.platform, context.cookies())
            except Exception:
                pass
            context.close()
            browser.close()

        return inserted

    @staticmethod
    def _wait_job_cards(page: Page, timeout_ms: int = 20_000) -> None:
        # Some Liepin card nodes are present but not considered visible by Playwright.
        # Wait for DOM attachment first, then fallback to count polling.
        try:
            page.locator(JOB_CARDS_SELECTOR).first.wait_for(state="attached", timeout=timeout_ms)
            return
        except Exception:
            end_at = time.time() + timeout_ms / 1000
            while time.time() < end_at:
                if page.locator(JOB_CARDS_SELECTOR).count() > 0:
                    return
                time.sleep(0.2)
        raise TimeoutError(f"wait job cards timeout after {timeout_ms}ms")

    @staticmethod
    def _wait_keyword_results(page: Page, keyword: str, timeout_ms: int = 20_000) -> None:
        encoded = urllib.parse.quote(keyword, safe="")
        end_at = time.time() + timeout_ms / 1000
        while time.time() < end_at:
            url = page.url or ""
            if f"key={encoded}" in url and "scene=input" in url:
                return
            time.sleep(0.2)
        raise TimeoutError(f"wait keyword result timeout after {timeout_ms}ms")

    def _submit_keyword_search(self, page: Page, keyword: str) -> None:
        search_input = self._find_keyword_input(page, timeout_ms=20_000)
        if search_input is None:
            raise RuntimeError(f"未找到猎聘关键词输入框: url={page.url}")

        try:
            current_value = (search_input.input_value() or "").strip()
        except Exception:
            current_value = ""

        try:
            search_input.click()
            if current_value != keyword:
                search_input.fill("")
                search_input.fill(keyword)
            search_input.press("Enter")
            self.emit_progress("已在页面内提交关键词搜索")
        except Exception as exc:
            raise RuntimeError(f"猎聘关键词提交失败: {exc}") from exc

    def _parse_search_json(self, text: str, keyword: str, save_raw: bool) -> list[dict[str, Any]]:
        try:
            root = json.loads(text)
        except Exception:
            return []

        data = root.get("data")
        if not isinstance(data, dict):
            return []
        card_list = data.get("data", {}).get("jobCardList") if isinstance(data.get("data"), dict) else None
        if not isinstance(card_list, list):
            card_list = data.get("jobCardList")
        if not isinstance(card_list, list):
            return []

        rows: list[dict[str, Any]] = []
        for item in card_list:
            if not isinstance(item, dict):
                continue
            job = item.get("job") if isinstance(item.get("job"), dict) else {}
            comp = item.get("comp") if isinstance(item.get("comp"), dict) else {}
            recruiter = item.get("recruiter") if isinstance(item.get("recruiter"), dict) else {}
            job_id = job.get("jobId")
            post_desc = None
            req_text = self._first_text(
                job,
                ["require", "requirement", "jobRequirement", "positionRequirement", "requireSkills"],
            ) or self._first_text(
                item,
                ["require", "requirement", "jobRequirement", "positionRequirement", "requireSkills"],
            )
            req_text = self._normalize_text(req_text)
            raw_job_link = (
                job.get("link")
                or job.get("jobLink")
                or job.get("jobHref")
                or item.get("link")
                or item.get("jobLink")
            )
            job_link = self._normalize_job_link(raw_job_link, job_id)

            row: dict[str, Any] = {
                "platform": "liepin",
                "keyword": keyword,
                "encrypt_id": str(job_id) if job_id is not None else None,
                "job_name": job.get("title"),
                "salary_desc": job.get("salary"),
                "location_name": job.get("dq"),
                "experience_name": job.get("requireWorkYears"),
                "degree_name": job.get("requireEduLevel"),
                "post_description": post_desc,
                "post_requirements": req_text,
                "job_link": job_link,
                "company_name": comp.get("compName"),
                "boss_name": recruiter.get("recruiterName"),
                "boss_title": recruiter.get("recruiterTitle"),
                "raw_json": item if save_raw else None,
            }
            rows.append(row)
        return rows

    @staticmethod
    def _first_text(src: dict[str, Any], keys: list[str]) -> str | None:
        for k in keys:
            v = src.get(k)
            if isinstance(v, str) and v.strip():
                return v.strip()
        return None

    @staticmethod
    def _normalize_text(v: str | None) -> str | None:
        if not v:
            return None
        s = re.sub(r"<[^>]+>", " ", v)
        s = re.sub(r"\s+", " ", s).strip()
        return s or None

    @staticmethod
    def _normalize_job_link(raw_link: Any, job_id: Any) -> str | None:
        canonical = f"https://www.liepin.com/job/{job_id}.shtml" if job_id is not None else None

        if not isinstance(raw_link, str) or not raw_link.strip():
            return canonical

        link = raw_link.strip()
        if link.startswith("//"):
            link = f"https:{link}"
        elif link.startswith("/"):
            link = f"https://www.liepin.com{link}"

        try:
            parsed = urllib.parse.urlparse(link)
            host = (parsed.netloc or "").lower()
            path = (parsed.path or "").lower()
            # Drop tracking/marketing pages; keep canonical detail URL instead.
            if "wow.liepin.com" in host and canonical:
                return canonical
            if "liepin.com" in host and ("/job/" in path or "/a/" in path):
                return link
        except Exception:
            pass

        return canonical or link

    @staticmethod
    def _find_keyword_input(page: Page, timeout_ms: int = 5_000):
        candidates = [
            "input[placeholder='搜索职位、公司']",
            "input[placeholder*='职位']",
            "input[placeholder*='关键词']",
            "input[placeholder*='搜索']",
            "input[name='key']",
            "input[name='keyword']",
            "input[type='search']",
            "input[type='text']",
        ]
        end_at = time.time() + timeout_ms / 1000
        while time.time() < end_at:
            for sel in candidates:
                try:
                    lc = page.locator(sel)
                    if lc.count() == 0:
                        continue
                    first = lc.first
                    if first.is_visible() and first.is_enabled():
                        return first
                except Exception:
                    continue
            time.sleep(0.2)
        return None

    @staticmethod
    def _pause(step_wait_sec: float) -> None:
        if step_wait_sec > 0:
            time.sleep(step_wait_sec)
