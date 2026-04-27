import re
import threading
import time
import urllib.parse
from datetime import datetime
from typing import Any

from playwright.sync_api import Page, sync_playwright

from app.repository.cookie_repo import get_platform_cookies, save_platform_cookies
from app.repository.jobs_repo import insert_job
from app.services.job_platform_service import JobPlatformService

ZHILIAN_HOME_URL = "https://www.zhaopin.com/sou/"
CARD_SELECTOR = "div.joblist-box__item"
NEXT_SELECTOR = 'a.soupager__btn:has-text("下一页")'


class ZhilianPlatformService(JobPlatformService):
    def __init__(self):
        super().__init__(platform="zhilian")
        self._thread: threading.Thread | None = None

    def start(self, payload: dict[str, Any]) -> None:
        if self.state.running:
            raise RuntimeError("Zhilian task is already running")
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
        city_code = str(payload.get("city_code", "489")).strip()
        salary = str(payload.get("salary", "")).strip()
        max_pages = int(payload.get("max_pages", 30))
        headless = bool(payload.get("headless", False))
        slow_mo = int(payload.get("slow_mo", 50))
        step_wait_sec = float(payload.get("step_wait_sec", max(slow_mo, 0) / 1000))
        save_raw = bool(payload.get("save_raw_json", False))

        base_url = self._build_base_url(keyword=keyword, city_code=city_code, salary=salary, page_num=1)
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
            page.goto(base_url, wait_until="domcontentloaded", timeout=60_000)

            if self._is_script_error_page(page):
                raise RuntimeError(f"智联结果页返回脚本错误: url={page.url}")

            if not self._url_has_keyword(page, keyword):
                self._submit_keyword_search(page, keyword)

            self._wait_keyword_results(page, keyword, timeout_ms=20_000)

            page.wait_for_selector(CARD_SELECTOR, timeout=20_000)
            self._stabilize_page(step_wait_sec=step_wait_sec)

            for _ in range(max_pages):
                if self.stop_event.is_set():
                    self.emit_progress("采集中止")
                    break

                inserted += self._collect_current_page(
                    page=page,
                    keyword=keyword,
                    save_raw=save_raw,
                    seen=seen,
                )

                next_btn = page.locator(NEXT_SELECTOR)
                if next_btn.count() == 0:
                    break
                cls = (next_btn.first.get_attribute("class") or "").lower()
                if "disabled" in cls:
                    break

                try:
                    next_btn.first.scroll_into_view_if_needed()
                    next_btn.first.click()
                    page.wait_for_selector(CARD_SELECTOR, timeout=20_000)
                    self._stabilize_page(step_wait_sec=step_wait_sec)
                    self.emit_progress("翻页采集中")
                except Exception:
                    break

            try:
                save_platform_cookies(self.platform, context.cookies())
            except Exception:
                pass
            context.close()
            browser.close()

        return inserted

    def _collect_current_page(
        self,
        *,
        page: Page,
        keyword: str,
        save_raw: bool,
        seen: set[str],
    ) -> int:
        cards = page.locator(CARD_SELECTOR)
        count = cards.count()
        inserted = 0
        for i in range(count):
            if self.stop_event.is_set():
                break
            card = cards.nth(i)
            title = self._safe_text(card, "a.jobinfo__name")
            link = self._safe_attr(card, "a.jobinfo__name", "href")
            salary = self._safe_text(card, "p.jobinfo__salary")
            location = self._safe_text(card, "div.jobinfo__other-info div.jobinfo__other-info-item > span")
            experience = self._safe_text(card, "div.jobinfo__other-info-item:nth-child(2)")
            degree = self._safe_text(card, "div.jobinfo__other-info-item:nth-child(3)")
            company = self._safe_text(card, "div.companyinfo__name")
            job_id = self._extract_job_id_from_link(link)
            requirements = " / ".join(
                [x for x in [experience, degree] if isinstance(x, str) and x.strip()]
            )

            if job_id and job_id in seen:
                continue
            if job_id:
                seen.add(job_id)

            row: dict[str, Any] = {
                "platform": "zhilian",
                "keyword": keyword,
                "encrypt_id": job_id,
                "job_name": title,
                "salary_desc": salary,
                "location_name": location,
                "experience_name": experience,
                "degree_name": degree,
                "post_description": None,
                "post_requirements": requirements or None,
                "job_link": link,
                "company_name": company,
                "boss_name": None,
                "boss_title": None,
                "raw_json": {
                    "job_link": link,
                    "title": title,
                    "company": company,
                }
                if save_raw
                else None,
            }
            if insert_job(row):
                inserted += 1
                if inserted % 10 == 0:
                    self.emit_progress(f"已采集 {inserted} 条", current=i + 1, total=count)
        return inserted

    @staticmethod
    def _build_base_url(keyword: str, city_code: str, salary: str, page_num: int) -> str:
        url = (
            f"{ZHILIAN_HOME_URL}jl{urllib.parse.quote(city_code, safe='')}/"
            f"kw{urllib.parse.quote(keyword, safe='')}/p{page_num}"
        )
        query: list[str] = []
        if salary:
            query.append(f"sl={urllib.parse.quote(salary, safe='')}")
        if query:
            return f"{url}?{'&'.join(query)}"
        return url

    @staticmethod
    def _url_has_keyword(page: Page, keyword: str) -> bool:
        keyword_lower = keyword.strip().lower()
        if not keyword_lower:
            return False

        try:
            search_input = page.locator("input[placeholder='输入职位、公司等搜索']").first
            input_value = (search_input.input_value() or "").strip().lower()
            if input_value == keyword_lower:
                return True
        except Exception:
            pass

        try:
            title = (page.title() or "").strip().lower()
            if keyword_lower in title and page.locator(CARD_SELECTOR).count() > 0:
                return True
        except Exception:
            pass

        url = (page.url or "").lower()
        return keyword_lower in url

    @staticmethod
    def _is_script_error_page(page: Page) -> bool:
        try:
            body_text = (page.locator("body").text_content() or "").strip().lower()
        except Exception:
            return False
        return "error return from script" in body_text

    @staticmethod
    def _wait_keyword_results(page: Page, keyword: str, timeout_ms: int = 20_000) -> None:
        end_at = time.time() + timeout_ms / 1000
        while time.time() < end_at:
            if ZhilianPlatformService._url_has_keyword(page, keyword):
                return
            time.sleep(0.2)
        raise TimeoutError(f"wait zhilian keyword result timeout after {timeout_ms}ms: url={page.url}")

    def _submit_keyword_search(self, page: Page, keyword: str) -> None:
        search_input = self._find_keyword_input(page, timeout_ms=20_000)
        if search_input is None:
            raise RuntimeError(f"未找到智联关键词输入框: url={page.url}")

        try:
            search_input.click()
            search_input.fill("")
            search_input.fill(keyword)
            search_input.press("Enter")
            self.emit_progress("已在页面内提交智联关键词搜索")
        except Exception as exc:
            raise RuntimeError(f"智联关键词提交失败: {exc}") from exc

    @staticmethod
    def _extract_job_id_from_link(link: str | None) -> str | None:
        if not link:
            return None
        m = re.search(r"jobdetail/([^/?]+)", link)
        return m.group(1) if m else None

    @staticmethod
    def _safe_text(node: Any, selector: str) -> str | None:
        try:
            txt = node.locator(selector).first.text_content()
            return txt.strip() if txt else None
        except Exception:
            return None

    @staticmethod
    def _safe_attr(node: Any, selector: str, attr: str) -> str | None:
        try:
            v = node.locator(selector).first.get_attribute(attr)
            return v.strip() if isinstance(v, str) and v.strip() else None
        except Exception:
            return None

    @staticmethod
    def _find_keyword_input(page: Page, timeout_ms: int = 5_000):
        candidates = [
            "input[placeholder='输入职位、公司等搜索']",
            "input[placeholder*='职位']",
            "input[placeholder*='公司']",
            "input[name='kw']",
            "input[type='text']",
            "input[class*='search'], input[class*='sou'], input[class*='input']",
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
    def _stabilize_page(step_wait_sec: float) -> None:
        if step_wait_sec > 0:
            time.sleep(step_wait_sec)
