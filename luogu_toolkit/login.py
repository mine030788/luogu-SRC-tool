"""login.py - 洛谷账号密码登录 (Playwright + ddddocr + 2FA)

从 luoguAI/luogu-api-python/pw_login.py 重构而来, 去掉了 web 耦合:

  - 不再写 /tmp/luogu_after_login.html 等中间文件
  - 不依赖全局 Flask app / session / task store
  - 暴露纯 Python API, 既可给 CLI 用, 也可给 Web UI 用

用法 (SDK):
    from luogu_toolkit import login_with_password, get_login_status, save_cookies

    result = login_with_password("user", "pass")
    if result["state"] == "need_2fa":
        sid = result["session_id"]
        # ... 等用户在终端/网页输入 2FA ...
        result = login_with_password(session_id=sid, totp_code="123456")
    if result["state"] == "done":
        save_cookies(result["cookies"])  # 落盘到 ~/.luogu-toolkit/cookies.json
"""
from __future__ import annotations

import logging
import os
import re
import sys
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

logger = logging.getLogger("luogu_toolkit.login")

# ── 配置 (从环境变量覆盖) ──
MAX_CAPTCHA_AUTO = int(os.environ.get("PWD_LOGIN_MAX_CAPTCHA", "6"))
SESSION_TTL = int(os.environ.get("PWD_LOGIN_TTL", "300"))  # 5 分钟
PWD_LOGIN_USE_CHROME = os.environ.get("PWD_LOGIN_USE_CHROME", "1") == "1"
PWD_LOGIN_HEADLESS = os.environ.get("PWD_LOGIN_HEADLESS", "new")
# 手动接管: OCR 失败时把浏览器留给你自己填验证码 (默认关闭)
MANUAL_FALLBACK = os.environ.get("PWD_LOGIN_MANUAL_FALLBACK", "0") == "1"

# ── ddddocr 单例 (启动期导入, OCR 引擎 ≈ 30MB) ──
_OCR = None
_OCR_LOCK = threading.Lock()


def _get_ocr():
    global _OCR
    with _OCR_LOCK:
        if _OCR is None:
            import ddddocr  # type: ignore
            _OCR = ddddocr.DdddOcr(show_ad=False)
    return _OCR


# ═══════════════════════════════════════════════════════════════════════
#  LoginSession: 一个登录请求对应的 Playwright 浏览器会话
# ═══════════════════════════════════════════════════════════════════════


@dataclass
class LoginSession:
    """单个登录请求的浏览器会话。线程安全。

    Attributes:
        session_id: UUID, 用于轮询状态
        username / password: 凭据
        state: idle / starting / captcha / need_2fa / done / failed
        message: 人类可读进度
        error: 失败原因
        cookies: 成功后写入 {__client_id, _uid, C3VK}
    """

    session_id: str
    username: str
    password: str
    state: str = "idle"
    message: str = ""
    error: str = ""
    cookies: Dict[str, str] = field(default_factory=dict)
    captcha_attempts: int = 0
    created_at: float = field(default_factory=time.time)

    # 内部 Playwright 对象 (不序列化)
    _pw: Any = field(default=None, repr=False)
    _browser: Any = field(default=None, repr=False)
    _context: Any = field(default=None, repr=False)
    _page: Any = field(default=None, repr=False)
    _thread: Optional[threading.Thread] = field(default=None, repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    # ── 状态查询 ──

    def to_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "state": self.state,
            "message": self.message,
            "error": self.error,
            "cookies": self.cookies,
            "captcha_attempts": self.captcha_attempts,
            "need_2fa": self.state == "need_2fa",
            "expired": self.is_expired(),
        }

    def is_expired(self) -> bool:
        return (time.time() - self.created_at) > SESSION_TTL

    # ── 启动 / 等待 ──

    def start(self) -> None:
        self.state = "starting"
        self.message = "正在启动浏览器…"
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def join(self, timeout: float = 60.0) -> None:
        if self._thread:
            self._thread.join(timeout=timeout)

    # ── 2FA 提交 ──

    def submit_2fa(self, code: str) -> bool:
        """2FA 阶段: 在已打开的 page 上填 6 位验证码并提交"""
        with self._lock:
            if self.state != "need_2fa":
                return False
            code = (code or "").strip()
            if not code or len(code) != 6 or not code.isdigit():
                self.error = "2FA 验证码必须是 6 位数字"
                return False
        t = threading.Thread(target=self._submit_2fa_run, args=(code,), daemon=True)
        t.start()
        return True

    # ── 关闭 ──

    def close(self) -> None:
        try:
            if self._context is not None:
                self._context.close()
        except Exception:
            pass
        try:
            if self._browser is not None:
                self._browser.close()
        except Exception:
            pass
        try:
            if self._pw is not None:
                self._pw.stop()
        except Exception:
            pass

    # ══════════════════════════════════════════════════════════════════
    #  后台线程: Playwright 跑登录
    # ══════════════════════════════════════════════════════════════════

    def _run(self) -> None:
        try:
            from playwright.sync_api import sync_playwright
        except Exception as e:
            self._fail(f"Playwright 未安装: {e}")
            return

        try:
            with sync_playwright() as pw:
                self._pw = pw
                launch_kwargs = dict(
                    args=[
                        "--no-sandbox",
                        "--disable-dev-shm-usage",
                        "--disable-blink-features=AutomationControlled",
                    ],
                    chromium_sandbox=False,
                )
                browser = None
                if PWD_LOGIN_USE_CHROME:
                    for ch in ("chrome", "chromium"):
                        try:
                            browser = pw.chromium.launch(channel=ch, **launch_kwargs)
                            logger.info("使用了 channel=%s", ch)
                            break
                        except Exception as e:
                            logger.info("channel=%s 不可用: %s", ch, str(e)[:100])
                if browser is None:
                    browser = pw.chromium.launch(
                        headless=(PWD_LOGIN_HEADLESS not in (False, "no", "0")),
                        **launch_kwargs,
                    )
                    logger.info("使用 Playwright 自带 chromium")
                self._browser = browser
                context = browser.new_context(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                               "AppleWebKit/537.36 (KHTML, like Gecko) "
                               "Chrome/120.0.0.0 Safari/537.36",
                    viewport={"width": 1280, "height": 860},
                    locale="zh-CN",
                )
                self._context = context
                page = context.new_page()
                self._page = page

                # --- Step 1: 登录页 + 用户名 ---
                self._set_msg("正在打开洛谷登录页…")
                page.goto("https://www.luogu.com.cn/auth/login",
                          wait_until="domcontentloaded", timeout=30000)
                page.locator("input[autocomplete='username webauthn']").fill(self.username)
                time.sleep(0.4)
                page.locator("button.solid.lform-size-middle")\
                    .filter(has_text="下一步").first.click()
                time.sleep(1.2)

                # --- Step 2: 等待密码框 + 验证码 ---
                try:
                    page.wait_for_selector("input[type='password']", timeout=10000)
                    page.wait_for_selector("img[src*='/lg4/captcha']", timeout=10000)
                except Exception as e:
                    self._fail(f"未进入 step-2 (密码 + 验证码): {e}")
                    return
                time.sleep(0.5)

                # --- Step 3: OCR 验证码 + 提交 (重试) ---
                if not self._try_login_with_captcha(page, max_attempts=MAX_CAPTCHA_AUTO):
                    # 手动接管模式: 浏览器保持打开, 让用户自己填验证码
                    if MANUAL_FALLBACK:
                        self._set_msg(
                            f"OCR 失败 {MAX_CAPTCHA_AUTO} 次 — 浏览器已留给你手动接管, "
                            "填完验证码后点『完成』, 工具会继续抓 cookies"
                        )
                        self._wait_for_user_handoff(page)
                        # 用户手动完成后, 再走 2FA 检测 + C3VK 抓取
                        time.sleep(2)
                        html = page.content()
                        if self._looks_like_2fa(html):
                            self._set_need_2fa()
                            return
                        if self._looks_like_login_error(html):
                            err = self._extract_swal_text(html) or "登录失败"
                            self._fail(err)
                            return
                        self._set_msg("手动接管完成, 正在抓 cookies…")
                        for u in [
                            "https://www.luogu.com.cn/",
                            "https://www.luogu.com.cn/user/settings",
                            "https://www.luogu.com.cn/record/list",
                        ]:
                            try:
                                page.goto(u, wait_until="domcontentloaded", timeout=15000)
                                time.sleep(1.0)
                            except Exception:
                                pass
                        self._extract_and_done(page)
                        return
                    return

                # --- Step 4: 检测结果 ---
                time.sleep(2)
                html = page.content()
                if self._looks_like_2fa(html):
                    self._set_need_2fa()
                    return
                if self._looks_like_login_error(html):
                    err = self._extract_swal_text(html) or "登录失败"
                    self._fail(err)
                    return
                if "/auth/login" in page.url:
                    self._fail("登录未跳转, 请检查账号状态")
                    return

                # --- Step 5: 触发 C3VK 发放 ---
                self._set_msg("登录成功, 正在提取 Cookies…")
                for u in [
                    "https://www.luogu.com.cn/",
                    "https://www.luogu.com.cn/user/settings",
                    "https://www.luogu.com.cn/record/list",
                ]:
                    try:
                        page.goto(u, wait_until="domcontentloaded", timeout=15000)
                        time.sleep(1.0)
                    except Exception:
                        pass
                time.sleep(1.0)

                # --- Step 6: 提取三参数 (5 重兜底) ---
                self._extract_and_done(page)
        except Exception as e:
            logger.exception("login _run failed")
            self._fail(f"登录流程异常: {str(e)[:200]}")
        finally:
            if self.state in ("done", "failed"):
                self.close()

    def _submit_2fa_run(self, code: str) -> None:
        page = self._page
        if page is None:
            self._fail("2FA 会话已失效, 请重试登录")
            return
        try:
            totp_input = page.locator(
                "input[inputmode='numeric'], input[autocomplete='one-time-code'], "
                "input[maxlength='6']"
            ).first
            totp_input.fill(code)
            time.sleep(0.3)
            for txt in ("确定", "提交", "登录", "验证"):
                btn = page.get_by_role("button", name=txt)
                if btn.count() > 0:
                    try:
                        btn.first.click(timeout=2000)
                        break
                    except Exception:
                        continue
            time.sleep(3)

            html = page.content()
            if self._looks_like_2fa(html):
                self._fail("2FA 验证码错误或已过期, 请重新登录")
                return
            if "/auth/login" in page.url:
                err = self._extract_swal_text(html) or "2FA 提交后未跳转"
                self._fail(err)
                return

            self._set_msg("2FA 验证成功, 提取 Cookies…")
            for u in [
                "https://www.luogu.com.cn/",
                "https://www.luogu.com.cn/user/settings",
                "https://www.luogu.com.cn/record/list",
            ]:
                try:
                    page.goto(u, wait_until="domcontentloaded", timeout=15000)
                    time.sleep(1.0)
                except Exception:
                    pass
            self._extract_and_done(page)
        except Exception as e:
            self._fail(f"2FA 提交流程异常: {str(e)[:200]}")
        finally:
            if self.state in ("done", "failed"):
                self.close()

    # ══════════════════════════════════════════════════════════════════
    #  内部 helpers
    # ══════════════════════════════════════════════════════════════════

    def _try_login_with_captcha(self, page, max_attempts: int) -> bool:
        try:
            ocr = _get_ocr()
        except Exception as e:
            self._fail(f"ddddocr 未安装: {e}")
            return False

        for attempt in range(1, max_attempts + 1):
            self.captcha_attempts = attempt
            self._set_msg(f"自动识别图形验证码… (第 {attempt}/{max_attempts} 次)")

            captcha_img = page.locator("img[src*='/lg4/captcha']").first
            try:
                png = captcha_img.screenshot(type="png")
            except Exception as e:
                self._fail(f"截验证码失败: {e}")
                return False
            code = ocr.classification(png)
            logger.info("captcha attempt=%d ocr=%r", attempt, code)
            if not code or len(code) < 4:
                continue

            page.locator("input[type='password']").fill(self.password)
            page.locator("input[placeholder='请输入图形验证码']").fill(code)
            time.sleep(0.2)
            page.locator("button.solid.lform-size-middle")\
                .filter(has_text="使用账户密码登录").first.click()
            time.sleep(2.5)

            html = page.content()
            if "图形验证码错误" in html:
                if page.locator(".swal2-confirm").count() > 0:
                    try:
                        page.locator(".swal2-confirm").first.click(timeout=2000)
                        time.sleep(0.4)
                    except Exception:
                        pass
                try:
                    page.locator("img[src*='/lg4/captcha']").first.click()
                    time.sleep(0.6)
                except Exception:
                    pass
                continue
            if "请输入图形验证码" in html and "请输入" in html:
                if page.locator(".swal2-confirm").count() > 0:
                    try:
                        page.locator(".swal2-confirm").first.click(timeout=2000)
                    except Exception:
                        pass
                continue
            if "账号或密码错误" in html or "密码错误" in html or "用户不存在" in html:
                err = self._extract_swal_text(html) or "账号或密码错误"
                self._fail(err)
                return False
            return True
        # OCR 全部失败 — 引导用户走手动接管或手动填 cookies
        self._fail(
            f"自动识别图形验证码连续 {max_attempts} 次失败 "
            "(洛谷验证码可能换类型了). 两种救生圈:\n"
            "  ① 重启 web 时设 PWD_LOGIN_MANUAL_FALLBACK=1, "
            "浏览器会一直开着, 把验证码控制权交给你\n"
            "  ② 直接到 /login 用『方式 B · 手动填 cookies』"
            "粘贴 3 个 cookie 即可跳过验证码"
        )
        return False

    def _looks_like_2fa(self, html: str) -> bool:
        return (
            ("两步验证" in html and "验证" in html)
            or "二次验证" in html
            or ("6 位" in html and "验证" in html)
        )

    def _looks_like_login_error(self, html: str) -> bool:
        return any(k in html for k in (
            "账号或密码错误", "密码错误", "用户不存在", "账号不存在",
        ))

    def _wait_for_user_handoff(self, page, max_wait: int = 300) -> None:
        """OCR 失败后, 把浏览器留给用户自己填验证码.

        判定"用户已完成"的条件 (满足任一即认为完成):
          - URL 离开了 /auth/login (登录成功跳转)
          - 页面出现两步验证提示
        """
        self._set_msg(
            f"⏳ 浏览器已留在你眼前, 手动填完验证码点登录. "
            f"最长等 {max_wait} 秒…"
        )
        # 先把 headless 关掉, 弹个真窗口出来
        try:
            page.bring_to_front()
        except Exception:
            pass
        deadline = time.time() + max_wait
        while time.time() < deadline:
            time.sleep(2)
            if self.state in ("done", "failed", "expired"):
                return
            try:
                url = page.url
            except Exception:
                continue
            if "/auth/login" not in url:
                # 已经跳走 — 让外层流程抓 cookies
                return
            try:
                html = page.content()
            except Exception:
                continue
            if self._looks_like_2fa(html):
                return
        self._fail(f"手动接管超时 ({max_wait} 秒), 自动放弃")

    def _extract_swal_text(self, html: str) -> str:
        m = re.search(r'class="swal2-html-container"[^>]*>([^<]+)<', html)
        if m:
            return m.group(1).strip()
        m = re.search(r'class="swal2-title"[^>]*>([^<]+)<', html)
        if m:
            return m.group(1).strip()
        return ""

    def _set_need_2fa(self) -> None:
        with self._lock:
            self.state = "need_2fa"
            self.message = "需要 2FA 验证码, 请输入 6 位数字"

    def _extract_and_done(self, page) -> None:
        try:
            cookies = {c["name"]: c["value"] for c in self._context.cookies()}
        except Exception as e:
            self._fail(f"读 cookies 失败: {e}")
            return

        client_id = cookies.get("__client_id", "")
        uid = cookies.get("_uid", "")
        c3vk = cookies.get("C3VK", "")

        # 兜底 0: window.userdata / window.C3VK
        if not c3vk:
            try:
                v = page.evaluate("""() => {
                    const out = {};
                    try { out.userdata_c3vk = window.userdata?.c3vk; } catch(e) {}
                    try { out.userdata_C3VK = window.userdata?.C3VK; } catch(e) {}
                    try { out.window_c3vk = window.c3vk; } catch(e) {}
                    try { out.window_C3VK = window.C3VK; } catch(e) {}
                    out.document_cookie = document.cookie;
                    return out;
                }""")
                if isinstance(v, dict):
                    for k in ("userdata_c3vk", "userdata_C3VK",
                              "window_c3vk", "window_C3VK"):
                        if v.get(k) and isinstance(v[k], str):
                            c3vk = v[k]
                            break
                    if not c3vk:
                        dc = v.get("document_cookie", "")
                        m = re.search(r"C3VK=([^;]+)", dc)
                        if m:
                            c3vk = m.group(1)
            except Exception as e:
                logger.debug("window extract failed: %s", e)

        # 兜底 1: /api/user/profile Set-Cookie
        if not c3vk and uid:
            try:
                resp = self._context.request.get(
                    f"https://www.luogu.com.cn/api/user/profile/{uid}",
                    headers={"Accept": "application/json"},
                )
                set_cookies = []
                if hasattr(resp.headers, "get_list"):
                    set_cookies = resp.headers.get_list("set-cookie")
                if not set_cookies and resp.headers.get("set-cookie"):
                    set_cookies = [resp.headers.get("set-cookie")]
                for sc in set_cookies:
                    m = re.search(r"C3VK=([^;]+);", sc)
                    if m:
                        c3vk = m.group(1)
                        break
            except Exception as e:
                logger.debug("profile Set-Cookie failed: %s", e)

        # 兜底 2: 二次访问首页
        if not c3vk:
            try:
                page.goto("https://www.luogu.com.cn/",
                          wait_until="domcontentloaded", timeout=15000)
                time.sleep(2)
                cookies = {c["name"]: c["value"] for c in self._context.cookies()}
                c3vk = cookies.get("C3VK", "")
            except Exception as e:
                logger.debug("revisit / failed: %s", e)

        # 兜底 3: csrf-token meta
        if not c3vk:
            try:
                html = page.content()
                m = re.search(r'<meta\s+name="csrf-token"\s+content="([^"]+)"', html)
                if m:
                    c3vk = m.group(1)
            except Exception as e:
                logger.debug("csrf-token meta failed: %s", e)

        # 兜底 4: /record/list HTML
        if not c3vk:
            try:
                page.goto("https://www.luogu.com.cn/record/list",
                          wait_until="domcontentloaded", timeout=15000)
                time.sleep(2)
                cookies = {c["name"]: c["value"] for c in self._context.cookies()}
                c3vk = cookies.get("C3VK", "")
            except Exception as e:
                logger.debug("revisit /record/list failed: %s", e)

        # 兜底 5: /api/user/me body
        if not c3vk:
            try:
                resp = self._context.request.get(
                    "https://www.luogu.com.cn/api/user/me",
                    headers={"Accept": "application/json"},
                )
                m = re.search(r'"C3VK"\s*:\s*"([^"]+)"', resp.text)
                if m:
                    c3vk = m.group(1)
            except Exception as e:
                logger.debug("/api/user/me failed: %s", e)

        if not (client_id and uid and c3vk):
            self._fail(
                f"提取三参数不完整: __client_id={'Y' if client_id else 'N'} "
                f"_uid={'Y' if uid else 'N'} C3VK={'Y' if c3vk else 'N'}"
            )
            return

        with self._lock:
            self.cookies = {
                "__client_id": client_id,
                "_uid": uid,
                "C3VK": c3vk,
            }
            self.state = "done"
            self.message = "登录成功, 已提取 Cookies"

    def _set_msg(self, msg: str) -> None:
        with self._lock:
            # need_2fa 状态不要覆盖 (用户在等 2FA 输入)
            if self.state != "need_2fa":
                self.message = msg

    def _fail(self, err: str) -> None:
        with self._lock:
            self.state = "failed"
            self.error = err
            self.message = f"失败: {err}"


# ═══════════════════════════════════════════════════════════════════════
#  LoginSessionManager: 全局单例, 管理所有进行中的会话
# ═══════════════════════════════════════════════════════════════════════


class LoginSessionManager:
    """管理所有进行中的 LoginSession。带 TTL 自动清理。"""

    def __init__(self) -> None:
        self._sessions: Dict[str, LoginSession] = {}
        self._lock = threading.Lock()

    def create(self, username: str, password: str) -> LoginSession:
        sid = uuid.uuid4().hex
        sess = LoginSession(
            session_id=sid, username=username, password=password,
        )
        with self._lock:
            self._sessions[sid] = sess
        self._gc()
        return sess

    def get(self, session_id: str) -> Optional[LoginSession]:
        with self._lock:
            return self._sessions.get(session_id)

    def remove(self, session_id: str) -> None:
        with self._lock:
            sess = self._sessions.pop(session_id, None)
        if sess:
            sess.close()

    def _gc(self) -> None:
        with self._lock:
            expired = [sid for sid, s in self._sessions.items() if s.is_expired()]
        for sid in expired:
            self.remove(sid)


# 全局单例
_MANAGER: Optional[LoginSessionManager] = None
_MGR_LOCK = threading.Lock()


def get_manager() -> LoginSessionManager:
    global _MANAGER
    with _MGR_LOCK:
        if _MANAGER is None:
            _MANAGER = LoginSessionManager()
        return _MANAGER


# ═══════════════════════════════════════════════════════════════════════
#  顶层便捷函数: 给 CLI / Web UI / SDK 共用
# ═══════════════════════════════════════════════════════════════════════


def login_with_password(
    username: Optional[str] = None,
    password: Optional[str] = None,
    totp_code: Optional[str] = None,
    session_id: Optional[str] = None,
) -> dict:
    """启动/继续 Playwright 登录 → 返回状态/cookies。

    Returns
    -------
    dict:
        - state='started', session_id='xxx', message='...' — 已启动, 需轮询
        - state='need_2fa', session_id='xxx' — 需要 2FA
        - state='done', cookies={__client_id, _uid, C3VK}, luogu_uid=1472806
        - state='failed', error='...' — 登录失败
        - state='expired' — session_id 找不到/已过期

    Examples
    --------
    >>> r = login_with_password("user", "pass")  # 启动登录
    >>> if r["state"] == "need_2fa":
    ...     r = login_with_password(session_id=r["session_id"], totp_code="123456")
    >>> if r["state"] == "done":
    ...     print(r["cookies"])
    """
    mgr = get_manager()

    if session_id:
        sess = mgr.get(session_id)
        if not sess or sess.is_expired():
            return {"state": "expired", "ok": False, "error": "登录会话已过期, 请重新开始"}
        if not totp_code:
            d = sess.to_dict()
            d["ok"] = False
            return d
        if not sess.submit_2fa(totp_code):
            return {"state": "failed", "ok": False, "error": "2FA 提交失败: 会话不在 need_2fa 状态"}
        # 等最多 15 秒
        for _ in range(60):
            time.sleep(0.25)
            if sess.state in ("done", "failed"):
                break
        if sess.state == "done":
            return {
                "state": "done",
                "ok": True,
                "cookies": sess.cookies,
                "luogu_uid": int(sess.cookies.get("_uid", 0)) if sess.cookies.get("_uid") else None,
            }
        if sess.state == "failed":
            return {"state": "failed", "ok": False, "error": sess.error or "2FA 验证失败"}
        return {"state": "submitted_2fa", "ok": False, "message": "2FA 已提交, 验证中…"}

    if not username or not password:
        return {"state": "failed", "ok": False, "error": "用户名和密码不能为空"}
    username = str(username).strip()
    password = str(password)

    sess = mgr.create(username, password)
    sess.start()
    return {
        "state": "started",
        "ok": False,
        "session_id": sess.session_id,
        "message": "登录中…",
    }


def get_login_status(session_id: str) -> dict:
    """查询 LoginSession 当前状态 (供前端轮询)"""
    mgr = get_manager()
    sess = mgr.get(session_id)
    if not sess:
        return {"state": "expired", "error": "会话不存在或已过期"}
    if sess.is_expired():
        mgr.remove(session_id)
        return {"state": "expired", "error": "会话已过期"}
    out = sess.to_dict()
    if sess.state == "done":
        out["cookies"] = sess.cookies
        out["luogu_uid"] = (
            int(sess.cookies.get("_uid", 0)) if sess.cookies.get("_uid") else None
        )
    return out


def cancel_login(session_id: str) -> dict:
    """取消一个进行中的登录会话"""
    mgr = get_manager()
    sess = mgr.get(session_id)
    if not sess:
        return {"ok": False, "error": "会话不存在"}
    mgr.remove(session_id)
    return {"ok": True, "message": "已取消"}
