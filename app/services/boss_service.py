import json
import threading
import time
import urllib.parse
from datetime import datetime
from typing import Any

from playwright.sync_api import Page, Response, sync_playwright

from app.config import BOSS_BASE_URL
from app.repository.cookie_repo import get_platform_cookies, save_platform_cookies
from app.repository.jobs_repo import insert_job
from app.services.job_platform_service import JobPlatformService

LIST_SELECTOR = "ul.rec-job-list"
CARD_SELECTOR = "ul.rec-job-list li.job-card-box"
DETAIL_URL_PART = "/wapi/zpgeek/job/detail.json"


class BossPlatformService(JobPlatformService):
    def __init__(self):
        super().__init__(platform="boss")
        self._thread: threading.Thread | None = None

    def start(self, payload: dict[str, Any]) -> None:
        if self.state.running:
            raise RuntimeError("Boss task is already running")
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
            count = self._collect(payload)
            self.state.last_count = count
            self.emit_progress(f"任务完成，新增 {count} 条")
        except Exception as exc:  # pragma: no cover
            self.state.last_error = str(exc)
            self.emit_progress(f"任务异常：{exc}")
        finally:
            self.state.running = False
            self.state.last_finished_at = datetime.now()

    def _collect(self, payload: dict[str, Any]) -> int:
        keyword = str(payload["keyword"]).strip()
        city_code = str(payload.get("city_code", "101010100")).strip()
        headless = bool(payload.get("headless", False))
        slow_mo = int(payload.get("slow_mo", 50))
        step_wait_sec = float(payload.get("step_wait_sec", max(slow_mo, 0) / 1000))
        save_raw = bool(payload.get("save_raw_json", False))
        extra_query = [x for x in payload.get("extra_query", []) if isinstance(x, str) and "=" in x]
        query = [
            f"city={urllib.parse.quote(city_code, safe='')}",
            f"query={urllib.parse.quote(keyword, safe='')}",
            *extra_query,
        ]
        url = f"{BOSS_BASE_URL}?{'&'.join(query)}"
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
            page.goto(url, wait_until="domcontentloaded", timeout=60_000)
            page.wait_for_selector(LIST_SELECTOR, timeout=60_000)

            self._scroll_until_loaded(page, step_wait_sec=step_wait_sec)
            page.evaluate("window.scrollTo(0, 0)")
            self._pause(step_wait_sec)

            count = page.locator(CARD_SELECTOR).count()
            self.emit_progress("列表加载完成", current=0, total=count)
            for i in range(count):
                if self.stop_event.is_set():
                    self.emit_progress("采集中止", current=i, total=count)
                    break
                response = self._click_and_wait_detail(page, i)
                if response is None:
                    continue
                row = self._parse_response(
                    response=response,
                    keyword=keyword,
                    save_raw=save_raw,
                )
                if row is None:
                    continue
                eid = row.get("encrypt_id")
                if isinstance(eid, str) and eid:
                    if eid in seen:
                        continue
                    seen.add(eid)
                if insert_job(row):
                    inserted += 1
                    if inserted % 5 == 0 or i == count - 1:
                        self.emit_progress(
                            f"已采集 {inserted} 条",
                            current=i + 1,
                            total=count,
                        )
                if i >= 5:
                    page.evaluate("window.scrollBy(0, 140)")
                    self._pause(step_wait_sec)

            try:
                save_platform_cookies(self.platform, context.cookies())
            except Exception:
                pass
            context.close()
            browser.close()

        return inserted

    def _scroll_until_loaded(self, page: Page, step_wait_sec: float, max_rounds: int = 5000) -> None:
        last_count = -1
        stable_tries = 0
        for _ in range(max_rounds):
            if self.stop_event.is_set():
                break
            footer = page.locator("div#footer, #footer")
            if footer.count() > 0 and footer.first.is_visible():
                break
            page.evaluate("() => window.scrollBy(0, Math.floor(window.innerHeight * 1.5))")
            current_count = page.locator(CARD_SELECTOR).count()
            if current_count == last_count:
                stable_tries += 1
            else:
                stable_tries = 0
            last_count = current_count
            if stable_tries >= 3:
                page.evaluate("() => window.scrollTo(0, document.body.scrollHeight)")
            self._pause(step_wait_sec)

    @staticmethod
    def _pause(step_wait_sec: float) -> None:
        if step_wait_sec > 0:
            time.sleep(step_wait_sec)

    def _click_and_wait_detail(self, page: Page, idx: int) -> Response | None:
        try:
            with page.expect_response(
                lambda r: bool(
                    r.url and DETAIL_URL_PART in r.url and r.request.method.upper() == "GET"
                ),
                timeout=30_000,
            ) as info:
                page.locator(CARD_SELECTOR).nth(idx).click()
            return info.value
        except Exception:
            return None

    def _parse_response(self, response: Response, keyword: str, save_raw: bool) -> dict[str, Any] | None:
        try:
            body = response.text()
            root = json.loads(body)
        except Exception:
            return None

        zp = root.get("zpData")
        if not isinstance(zp, dict):
            return None
        job_info = zp.get("jobInfo")
        if not isinstance(job_info, dict):
            return None
        brand = zp.get("brandComInfo") if isinstance(zp.get("brandComInfo"), dict) else {}
        boss = zp.get("bossInfo") if isinstance(zp.get("bossInfo"), dict) else {}

        labels = job_info.get("jobLabels") if isinstance(job_info.get("jobLabels"), list) else []
        labels_text = " / ".join([str(x).strip() for x in labels if str(x).strip()])
        skills = job_info.get("skills") if isinstance(job_info.get("skills"), list) else []
        skills_text = " / ".join([str(x).strip() for x in skills if str(x).strip()])
        req_parts = []
        if labels_text:
            req_parts.append(f"标签: {labels_text}")
        if skills_text:
            req_parts.append(f"技能: {skills_text}")

        encrypt_id = job_info.get("encryptId")
        detail_link = job_info.get("jobUrl") or job_info.get("href")
        if not detail_link and encrypt_id:
            detail_link = f"https://www.zhipin.com/job_detail/{encrypt_id}.html"

        row: dict[str, Any] = {
            "platform": "boss",
            "keyword": keyword,
            "encrypt_id": encrypt_id,
            "job_name": job_info.get("jobName"),
            "salary_desc": job_info.get("salaryDesc"),
            "location_name": job_info.get("locationName"),
            "experience_name": job_info.get("experienceName"),
            "degree_name": job_info.get("degreeName"),
            "post_description": job_info.get("postDescription"),
            "post_requirements": "\n".join(req_parts) if req_parts else None,
            "job_link": detail_link,
            "company_name": brand.get("brandName"),
            "boss_name": boss.get("name"),
            "boss_title": boss.get("title"),
            "raw_json": zp if save_raw else None,
        }
        return row
