"""cookie.py - 洛谷登录 cookie 的提取/验证/落盘/导入导出

洛谷登录态的"三参数"约定:
  - __client_id  (浏览器唯一标识, 每次清浏览器会变)
  - _uid         (洛谷数字 UID, 如 1472806)
  - C3VK         (C3VK 一次性 token, v3.9.60 后非必填, 但仍保留兼容)

用法:
    from luogu_toolkit import build_cookie_dict, save_cookies, load_cookies

    # 1) 用户手动复制粘贴(从浏览器 DevTools → Application → Cookies)
    cookies = build_cookie_dict({
        "client_id": "xxx",
        "uid": "123456",
        "c3vk": "",  # 留空也 OK
    })

    # 2) 落盘
    save_cookies(cookies, "~/.luogu-toolkit/cookies.json")

    # 3) 之后可以读
    cookies = load_cookies()  # 默认路径
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, Mapping, TypedDict, Union

# 类型: cookie 字典 (key 必须严格匹配洛谷期望的字段名)
class CookieDict(TypedDict, total=False):
    __client_id: str   # 注意 key 带下划线, 必须用 dict 字面量访问
    _uid: str
    C3VK: str


# v3.10 · 兼容 key 拼写变体
KEY_ALIASES = {
    "__client_id": "__client_id",
    "_uid": "_uid",
    "C3VK": "C3VK",
    "client_id": "__client_id",
    "uid": "_uid",
    "c3vk": "C3VK",
}


def build_cookie_dict(form: Mapping[str, Any]) -> CookieDict:
    """从表单/任意 dict 中提取三参数。

    Accepts both "client_id" (短名) 和 "__client_id" (长名) 两种 key,
    长名优先。

    Raises:
        ValueError: 缺少必填字段 (__client_id 或 _uid)
    """
    out: Dict[str, str] = {}

    # 1) 用 alias 表把用户传的 key 标准化
    for user_key, value in form.items():
        canonical = KEY_ALIASES.get(user_key)
        if not canonical or not value:
            continue
        out[canonical] = str(value).strip()

    # 2) 校验必填
    missing = []
    if not out.get("__client_id"):
        missing.append("__client_id")
    if not out.get("_uid"):
        missing.append("_uid")
    if missing:
        raise ValueError(
            f"Cookies 参数为必填项，请完整填写：{', '.join(missing)}"
        )

    # 3) C3VK 留空也允许 (v3.9.60+ 不再需要)
    out.setdefault("C3VK", "")

    return out  # type: ignore[return-value]


# 落盘默认路径 (按函数读, 便于环境变量覆盖)
DEFAULT_COOKIES_PATH = Path(
    os.environ.get("LUOGU_COOKIES_PATH", "").strip()
    or str(Path.home() / ".luogu-toolkit" / "cookies.json")
)


def _resolve_default_path() -> Path:
    """每次调用时读环境变量 LUOGU_COOKIES_PATH, 便于测试 monkeypatch"""
    p = os.environ.get("LUOGU_COOKIES_PATH", "").strip()
    return Path(p) if p else Path.home() / ".luogu-toolkit" / "cookies.json"


def save_cookies(
    cookies: CookieDict | Mapping[str, str],
    path: Union[str, Path, None] = None,
) -> Path:
    """把 cookies 写到 JSON 文件 (默认 ~/.luogu-toolkit/cookies.json)

    文件格式:
    {
        "version": 1,
        "uid": "123456",
        "cookies": {"__client_id": "...", "_uid": "...", "C3VK": "..."},
        "saved_at": "2026-06-22T03:30:00Z"
    }

    Returns: 实际写入的文件路径
    """
    p = Path(path) if path else _resolve_default_path()
    p.parent.mkdir(parents=True, exist_ok=True)

    # 兼容 build_cookie_dict 输出 (dict 包含 __client_id 等)
    cookie_dict = dict(cookies)
    if "__client_id" not in cookie_dict:
        raise ValueError("cookies 缺少 __client_id")

    payload = {
        "version": 1,
        "uid": cookie_dict.get("_uid", ""),
        "cookies": cookie_dict,
        "saved_at": _now_iso(),
    }
    p.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return p


def load_cookies(
    path: Union[str, Path, None] = None,
) -> CookieDict:
    """从 JSON 文件读 cookies, 不存在或格式错就抛 FileNotFoundError / ValueError"""
    p = Path(path) if path else _resolve_default_path()
    if not p.exists():
        raise FileNotFoundError(
            f"cookies 文件不存在: {p}\n"
            f"请先用 `luogu-toolkit login` 或 `luogu-toolkit web` 登录"
        )
    data = json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or "cookies" not in data:
        raise ValueError(f"cookies 文件格式错误: {p}")
    return build_cookie_dict(data["cookies"])


def cookies_to_header(cookies: CookieDict | Mapping[str, str]) -> str:
    """把 cookie dict 转成 HTTP `Cookie:` 头字符串"""
    return "; ".join(f"{k}={v}" for k, v in cookies.items() if v)


def cookies_fingerprint(cookies: CookieDict | Mapping[str, str]) -> str:
    """给 cookies 生成短指纹(uid 前 4 位 + __client_id 后 6 位), 用于日志脱敏"""
    uid = str(cookies.get("_uid", ""))
    cid = str(cookies.get("__client_id", ""))
    return f"uid={uid[:4]}***_cid=...{cid[-6:]}" if uid and cid else "empty"


# ── helpers ──
def _now_iso() -> str:
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
