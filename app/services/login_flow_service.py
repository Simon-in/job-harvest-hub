import time
from typing import Any

from playwright.sync_api import sync_playwright

from app.repository.cookie_repo import get_platform_cookies, save_platform_cookies
from app.services.progress_hub import progress_hub

LOGIN_URLS = {
    "boss": "https://www.zhipin.com/",
    "liepin": "https://www.liepin.com/",
    "zhilian": "https://passport.zhaopin.com/login",
}

HOME_URLS = {
    "boss": "https://www.zhipin.com/",
    "liepin": "https://www.liepin.com/",
    "zhilian": "https://www.zhaopin.com/",
}

LIEPIN_LOGIN_CANDIDATES = [
    "https://www.liepin.com/",
    "https://passport.liepin.com/",
    "https://www.liepin.com/user/login/",
]

LOGIN_PATH_HINTS = {
    "boss": ["/web/user", "login", "passport", "security-check", "captcha", "verify"],
    "liepin": ["passport.liepin.com", "login"],
    "zhilian": ["passport.zhaopin.com", "login"],
}

LOGIN_COOKIE_HINTS = {
    "boss": ["stoken", "wt2", "__zp"],
    "liepin": ["liepin_login", "acw_tc", "ltoken", "userid"],
    "zhilian": ["zhaopin", "zp_passport", "zp_token"],
}

LOGIN_COOKIE_MIN_HITS = {
    "boss": 1,
    "liepin": 2,
    "zhilian": 2,
}


def _is_login_like_url(platform: str, url: str) -> bool:
    url_l = (url or "").lower()
    hints = LOGIN_PATH_HINTS.get(platform, [])
    return any(h in url_l for h in hints)


def _auth_cookie_hits(platform: str, cookies: list[dict[str, Any]]) -> int:
    hints = LOGIN_COOKIE_HINTS.get(platform, [])
    if not hints:
        return 0
    hits = 0
    for c in cookies:
        n = str(c.get("name", "")).lower()
        if any(h in n for h in hints):
            hits += 1
    return hits


def _is_likely_logged_in(platform: str, current_url: str, cookies: list[dict[str, Any]]) -> bool:
    # Conservative heuristic with platform-specific threshold.
    min_hits = LOGIN_COOKIE_MIN_HITS.get(platform, 2)
    return _auth_cookie_hits(platform, cookies) >= min_hits and not _is_login_like_url(platform, current_url)


def _should_recover_boss_login(current_url: str, auth_hits: int) -> bool:
    if auth_hits >= 2:
        return False
    u = (current_url or "").lower()
    return any(k in u for k in ["/web/geek/job", "/web/geek/recommend", "/web/geek/chat"])


def _try_open_boss_login(page) -> bool:
    # Prefer human-like click path first to reduce anti-bot redirect sensitivity.
    selectors = [
        "a[href*='header-login']",
        "a:has-text('登录')",
        "button:has-text('登录')",
        "div:has-text('登录')",
    ]
    for sel in selectors:
        try:
            lc = page.locator(sel)
            if lc.count() > 0:
                lc.first.click(timeout=2000)
                time.sleep(0.8)
                return True
        except Exception:
            continue
    return False


def _try_open_liepin_login(page) -> bool:
    selectors = [
        "a[href*='passport']",
        "a[href*='login']",
        "a:has-text('登录')",
        "a:has-text('登录/注册')",
        "button:has-text('登录')",
        "div:has-text('登录')",
    ]
    for sel in selectors:
        try:
            lc = page.locator(sel)
            if lc.count() > 0:
                lc.first.click(timeout=2500)
                time.sleep(0.9)
                if _is_login_like_url("liepin", page.url):
                    return True
        except Exception:
            continue
    return _is_login_like_url("liepin", page.url)


def _open_liepin_login(page) -> bool:
    if _is_login_like_url("liepin", page.url):
        return True

    if _try_open_liepin_login(page):
        return True

    for candidate in LIEPIN_LOGIN_CANDIDATES:
        try:
            page.goto(candidate, wait_until="domcontentloaded", timeout=60_000)
            if _is_login_like_url("liepin", page.url):
                return True
            if _try_open_liepin_login(page):
                return True
        except Exception:
            continue
    return _is_login_like_url("liepin", page.url)


def run_login_flow(
    platform: str,
    timeout_sec: int = 180,
    use_existing_cookies: bool = False,
    finish_on_login: bool = True,
    boss_manual_mode: bool = False,
    manual_login_mode: bool = False,
) -> dict[str, Any]:
    url = (HOME_URLS if manual_login_mode else LOGIN_URLS).get(platform)
    if not url:
        raise ValueError(f"unsupported platform: {platform}")

    progress_hub.publish(platform, "开始登录流程，请在弹窗完成登录")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, slow_mo=50)
        context = browser.new_context(
            viewport={"width": 1440, "height": 900},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
            ),
        )
        existed = get_platform_cookies(platform)
        if use_existing_cookies and existed:
            try:
                context.add_cookies(existed)
                progress_hub.publish(platform, f"已注入历史 Cookie: {len(existed)} 条")
            except Exception:
                pass
        elif existed:
            progress_hub.publish(platform, f"已跳过历史 Cookie 注入（默认干净登录），历史条数: {len(existed)}")

        page = context.new_page()
        page.goto(url, wait_until="domcontentloaded", timeout=60_000)

        if manual_login_mode:
            progress_hub.publish(platform, "全平台手动登录模式：仅打开首页，请手动点击登录并完成验证")

        if platform == "boss" and not manual_login_mode:
            if boss_manual_mode:
                progress_hub.publish(platform, "Boss手动登录模式已启用：请手动点击登录并完成验证")
            else:
                clicked = _try_open_boss_login(page)
                if clicked:
                    progress_hub.publish(platform, "已通过页面入口触发登录")
                else:
                    try:
                        page.goto(
                            "https://www.zhipin.com/web/user/?ka=header-login",
                            wait_until="domcontentloaded",
                            timeout=60_000,
                        )
                    except Exception:
                        pass

        if platform == "liepin" and not manual_login_mode:
            opened = _open_liepin_login(page)
            if opened:
                progress_hub.publish(platform, "已打开猎聘登录入口")
            else:
                progress_hub.publish(platform, "未自动定位到猎聘登录页，请在当前页手动点击登录")

        progress_hub.publish(platform, f"请在 {timeout_sec}s 内完成登录")

        end_at = time.time() + timeout_sec
        last_report = 0
        finished_early = False
        stable_login_hits = 0
        last_boss_recover_at = 0.0
        closed_by_user = False
        while time.time() < end_at:
            if page.is_closed():
                progress_hub.publish(platform, "检测到登录页面已关闭，立即保存 Cookie")
                closed_by_user = True
                break

            remain = int(end_at - time.time())
            if remain % 15 == 0 and remain != last_report:
                last_report = remain
                progress_hub.publish(platform, f"登录等待中，剩余 {remain}s")

            current_url = ""
            try:
                current_url = page.url
            except Exception:
                current_url = ""
            cookies_now = context.cookies()
            auth_hits = _auth_cookie_hits(platform, cookies_now)

            if platform == "boss" and not manual_login_mode and not boss_manual_mode and _should_recover_boss_login(current_url, auth_hits):
                now = time.time()
                if now - last_boss_recover_at >= 8:
                    try:
                        page.goto(
                            "https://www.zhipin.com/web/user/?ka=header-login",
                            wait_until="domcontentloaded",
                            timeout=60_000,
                        )
                        progress_hub.publish(platform, "检测到页面跳到岗位页，已自动回拉登录页")
                        last_boss_recover_at = now
                        time.sleep(1)
                        continue
                    except Exception:
                        pass

            should_auto_finish = finish_on_login and not manual_login_mode and not (platform == "boss" and boss_manual_mode)
            if should_auto_finish:
                if _is_likely_logged_in(platform, current_url, cookies_now):
                    stable_login_hits += 1
                    if stable_login_hits >= 3:
                        progress_hub.publish(platform, "检测到已登录，提前结束等待并保存 Cookie")
                        finished_early = True
                        break
                else:
                    stable_login_hits = 0

            time.sleep(1)

        cookies: list[dict[str, Any]] = []
        can_save = False
        try:
            cookies = context.cookies()
            can_save = True
        except Exception:
            progress_hub.publish(platform, "无法读取当前 Cookie（浏览器可能已关闭），保留原有 Cookie")

        if can_save:
            save_platform_cookies(platform, cookies)
            progress_hub.publish(platform, f"登录流程结束，Cookie 已保存：{len(cookies)} 条")

        try:
            context.close()
        except Exception:
            pass
        try:
            browser.close()
        except Exception:
            pass

    return {
        "saved_cookie_count": len(cookies),
        "timeout_sec": timeout_sec,
        "used_existing_cookies": use_existing_cookies,
        "finished_early": finished_early,
        "finish_on_login": finish_on_login,
        "boss_manual_mode": boss_manual_mode,
        "manual_login_mode": manual_login_mode,
        "closed_by_user": closed_by_user,
    }
