"""fetch.py - 基础数据抓取 (包装内嵌的 pyLuogu = luogu_toolkit._pyluogu)

提供 4 个常用 fetch 函数:
  - fetch_user(uid)             → 用户信息
  - fetch_records(uid, page)    → 提交记录分页
  - fetch_problem(pid)          → 题目详情
  - fetch_passed_problems(uid)  → 已通过的题目列表
  - verify_cookies()            → 校验 cookies 是否有效

所有函数都接收 cookies dict (CookieDict 类型), 返回 dict 或 list[dict]。

用法 (SDK):
    from luogu_toolkit import load_cookies, fetch_user, fetch_records

    cookies = load_cookies()
    user = fetch_user(cookies)
    records = fetch_records(cookies, page=1, limit=20)
"""
from __future__ import annotations

import logging
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from io import BytesIO
from typing import Any, Dict, List, Optional, Union
from zipfile import ZipFile, ZIP_DEFLATED

from .cookie import CookieDict

logger = logging.getLogger("luogu_toolkit.fetch")

# pyLuogu 已内嵌为 luogu_toolkit._pyluogu, 总是可用
# (除非装包时把这个目录手动删了)
try:
    from . import _pyluogu  # type: ignore
    from ._pyluogu.errors import AuthenticationError, ForbiddenError, RequestError  # type: ignore
    _HAS_PYLUOGU = True
except Exception:  # pragma: no cover
    _pyluogu = None  # type: ignore
    AuthenticationError = Exception  # type: ignore
    ForbiddenError = Exception  # type: ignore
    RequestError = Exception  # type: ignore
    _HAS_PYLUOGU = False


def _require_pyluogu():
    if not _HAS_PYLUOGU:
        raise RuntimeError(
            "_pyluogu 子包不可用, 无法执行 fetch 操作。\n"
            "请检查 luogu_toolkit/_pyluogu/ 目录是否存在且完整\n"
            "(这是 pyLuogu 的内嵌副本, 安装 luogu-toolkit 时自动包含)"
        )


def _make_client(cookies: CookieDict) -> Any:
    """用 cookies 构造 luoguAPI client"""
    _require_pyluogu()
    cookie_obj = _pyluogu.LuoguCookies(cookies)
    return _pyluogu.luoguAPI(cookies=cookie_obj)


# ═══════════════════════════════════════════════════════════════════════
#  校验
# ═══════════════════════════════════════════════════════════════════════


def verify_cookies(cookies: CookieDict) -> dict:
    """校验 cookies 是否有效 (调 /api/user/me)

    Returns
    -------
    dict:
        - ok=True, uid, username  → 有效
        - ok=False, error='expired' / 'forbidden' / 'network'  → 失效
    """
    _require_pyluogu()
    try:
        client = _make_client(cookies)
        me = client.me()  # pyLuogu 真实 API: me() 返回 UserDetails
        return {
            "ok": True,
            "uid": me.uid,
            "username": me.name,  # pyLuogu UserDetails 没有 username 字段, 用 name 兜底
            "name": me.name,
        }
    except AuthenticationError as e:
        return {"ok": False, "error": "expired", "message": str(e)[:200]}
    except ForbiddenError as e:
        return {"ok": False, "error": "forbidden", "message": str(e)[:200]}
    except Exception as e:
        # 不只标 "network" — 真实原因可能是 pyLuogu 字段名变了 / 接口改版 /
        # C3VK 校验失败 / SSL 等等。前端必须能看到 message 才能 debug。
        logger.exception("verify_cookies failed")
        return {"ok": False, "error": "network", "message": str(e)[:200]}


# ═══════════════════════════════════════════════════════════════════════
#  用户 / 题目 / 记录
# ═══════════════════════════════════════════════════════════════════════


def fetch_user(cookies: CookieDict, uid: Optional[int] = None) -> dict:
    """获取用户信息

    Parameters
    ----------
    cookies : CookieDict
        洛谷 cookies (__client_id / _uid / C3VK)
    uid : int, optional
        不传则查自己, 否则查指定 UID

    Returns
    -------
    dict: 用户信息 (uid, username, name, avatar, slogan, etc.)
    """
    _require_pyluogu()
    client = _make_client(cookies)
    if uid is None:
        user = client.me()  # UserDetails
    else:
        user = client.get_user_info(uid)  # UserDetails
    # UserDetails 是 pyLuogu.types.UserDetails (pydantic model / dataclass)
    # 统一转 dict
    try:
        return dict(user)
    except Exception:
        # 退路: 手动挑字段
        out = {}
        for attr in ("uid", "username", "name", "slogan", "avatar",
                     "badge", "isAdmin", "isBanned", "color"):
            if hasattr(user, attr):
                out[attr] = getattr(user, attr)
        return out


def fetch_records(
    cookies: CookieDict,
    uid: Optional[int] = None,
    page: int = 1,
    limit: int = 20,
    status: Optional[int] = None,
) -> list[dict]:
    """分页拉提交记录

    Parameters
    ----------
    cookies : CookieDict
    uid : int, optional — 不传则查自己
    page : int — 页号, 从 1 开始
    limit : int — 每页条数 (1-50, 洛谷硬限制)
    status : int, optional — 评测状态过滤, 0=全部, 12=AC ...

    Returns
    -------
    list[dict]: 每条 record 含 record_id / pid / title / verdict / lang / time / memory
    """
    _require_pyluogu()
    if not 1 <= limit <= 50:
        raise ValueError(f"limit 必须在 1-50 之间, 实际 {limit}")
    client = _make_client(cookies)
    if uid is None:
        me = client.me()
        uid = me.uid
    # pyLuogu: get_record_list(page, uid, ...)
    # 重要 1: status 不是"范围"而是"具体状态值" (0=等待, 12=AC 等)
    #         想要全部记录必须 不传 status
    # 重要 2: 不能传 uid=... — pyLuogu 会同时发 uid=...&user="..." 两个参数
    #         (raw_params 不过滤), 洛谷 API 看到未知 uid 参数就返回空
    #         必须直接传 user=str(uid), 这样 pyLuogu 看到 user 已经有值就不会
    #         触发 "uid→user" 的转换, uid=None 被过滤掉
    try:
        kwargs: Dict[str, Any] = {"page": page, "user": str(uid)}
        if status is not None:
            kwargs["status"] = status
        resp = client.get_record_list(**kwargs)
    except Exception as e:
        logger.exception("get_record_list failed (page=%s, uid=%s, status=%s)", page, uid, status)
        raise
    # 响应是 RecordListRequestResponse, schema: {records: List[Record], count: int, perPage: int}
    # ⚠️ resp.records 直接是 list, 不是 dict, 不要再 .result (那是我搞混 get_user_practice 的)
    records = []
    if hasattr(resp, "records") and resp.records is not None:
        if isinstance(resp.records, list):
            records = resp.records
        else:
            # 兜底: 兼容 dict 形态
            records = getattr(resp.records, "result", None) \
                   or (resp.records.get("result") if isinstance(resp.records, dict) else None) \
                   or []
    elif isinstance(resp, dict):
        records = (
            resp.get("records", {}).get("result", [])
            if isinstance(resp.get("records"), dict)
            else resp.get("records", [])
        )
    out: list[dict] = []
    for r in (records or [])[:limit]:
        # Record 对象 / dict 都要支持
        def _get(obj, key, default=None):
            if isinstance(obj, dict):
                return obj.get(key, default)
            return getattr(obj, key, default)

        # problem 可能是 dict 也可能是对象
        prob = _get(r, "problem")
        pid = _get(prob, "pid") if prob is not None else _get(r, "pid")
        title = _get(prob, "title") if prob is not None else _get(r, "title")
        out.append({
            "record_id": _get(r, "id") or _get(r, "recordId"),
            "pid": pid,
            "title": title,
            "verdict": _get(r, "status"),
            "lang": _get(r, "language"),
            "time": _get(r, "time"),
            "memory": _get(r, "memory"),
            "submit_time": _get(r, "submitTime"),
        })
    return out


def fetch_record_source(cookies: CookieDict, rid: int | str) -> dict:
    """拉指定 record 的源码 (调 /record/<rid>)

    Returns
    -------
    dict:
        - rid        : int
        - pid        : str  (题号)
        - title      : str  (题目标题)
        - language   : int  (洛谷语言码)
        - status     : int  (0=AC, 12=AC 在洛谷, 0/12 因版本而异)
        - sourceCode : str  (源码全文, 拿不到可能为 None)
        - sourceCodeLength : int
        - time, memory, submitTime, score : 原样
    """
    _require_pyluogu()
    client = _make_client(cookies)
    try:
        resp = client.get_record(rid)
    except Exception as e:
        logger.exception("get_record failed (rid=%s)", rid)
        raise
    rec = resp.record if hasattr(resp, "record") else None
    if rec is None:
        return {"rid": rid, "sourceCode": None, "error": "no record in response"}

    # 兼容 dict / 对象
    def _g(obj, key, default=None):
        if obj is None:
            return default
        if isinstance(obj, dict):
            return obj.get(key, default)
        return getattr(obj, key, default)

    problem = _g(rec, "problem")
    return {
        "rid": _g(rec, "id", rid),
        "pid": _g(problem, "pid"),
        "title": _g(problem, "title"),
        "language": _g(rec, "language"),
        "status": _g(rec, "status"),
        "score": _g(rec, "score"),
        "time": _g(rec, "time"),
        "memory": _g(rec, "memory"),
        "submitTime": _g(rec, "submitTime"),
        "sourceCodeLength": _g(rec, "sourceCodeLength"),
        "sourceCode": _g(rec, "sourceCode"),
    }


# ──────────────────────────────────────────────────────────────────────────────
# 批量打包下载所有 record 的源码
# ──────────────────────────────────────────────────────────────────────────────

# 洛谷 language code → 文件扩展名
_LANG_EXT = {
    0: "txt", 1: "pas", 2: "c", 3: "cpp", 4: "py", 5: "java",
    6: "cs", 7: "go", 8: "rs", 9: "php", 10: "rb", 11: "js",
    12: "kt", 13: "hs", 14: "lua", 15: "pl", 16: "scala",
    17: "ml", 18: "fs", 19: "sh", 20: "py", 21: "cpp", 22: "cpp",
    23: "cpp", 24: "js", 25: "py", 26: "ts", 27: "cpp", 28: "c",
    29: "lisp", 30: "d", 31: "zig", 32: "dart", 33: "mojo",
}


def _safe_filename(name: str, max_len: int = 80) -> str:
    """清掉文件系统/zip 不允许的字符, 截断长度"""
    # 替换路径分隔符 + 不可见字符
    name = re.sub(r'[\\/:*?"<>|\r\n\t]', "_", name).strip()
    # 压缩连续下划线
    name = re.sub(r"_+", "_", name).strip("._ ")
    if not name:
        name = "untitled"
    return name[:max_len]


def _source_filename(pid: str, title: str, language: int | None) -> str:
    """P2433_深基1-2小学数学N合一.cpp"""
    ext = _LANG_EXT.get(int(language or 0), "txt")
    safe_title = _safe_filename(title or "untitled")
    safe_pid = _safe_filename(pid or "unknown", max_len=20)
    return f"{safe_pid}_{safe_title}.{ext}"


def fetch_records_with_source(cookies: CookieDict, page: int = 1, limit: int = 20,
                              max_workers: int = 8) -> List[Dict[str, Any]]:
    """拉 records + 并发拉每条 record 的源码

    Returns
    -------
    list of dict, 每条:
        rid, pid, title, language, status, submitTime, sourceCode (or None)
    """
    records = fetch_records(cookies, page=page, limit=limit)
    if not records:
        return []

    rids = [r.get("record_id") or r.get("id") for r in records]
    rids = [rid for rid in rids if rid is not None]
    if not rids:
        return []

    out_map: Dict[Any, Dict[str, Any]] = {}

    def _fetch_one(rid):
        try:
            return rid, fetch_record_source(cookies, rid)
        except Exception as e:
            logger.warning("fetch_record_source(%s) failed: %s", rid, e)
            return rid, {"rid": rid, "sourceCode": None, "error": str(e)[:120]}

    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = [ex.submit(_fetch_one, rid) for rid in rids]
        for fut in as_completed(futures):
            rid, data = fut.result()
            out_map[rid] = data

    out: List[Dict[str, Any]] = []
    for r in records:
        rid = r.get("record_id") or r.get("id")
        if rid is None:
            continue
        d = out_map.get(rid, {})
        out.append({
            "rid": rid,
            "pid": r.get("pid") or d.get("pid"),
            "title": r.get("title") or d.get("title"),
            "language": d.get("language"),
            "status": d.get("status") or r.get("verdict"),
            "submitTime": d.get("submitTime") or r.get("submit_time"),
            "sourceCode": d.get("sourceCode"),
            "sourceCodeLength": d.get("sourceCodeLength"),
            "error": d.get("error"),
        })
    return out


def fetch_all_records_with_source(cookies: CookieDict, per_page: int = 50,
                                   max_pages: int = 50, max_workers: int = 8) -> List[Dict[str, Any]]:
    """拉**所有** record + 它们的源码 (自动分页)

    流程: 循环调 fetch_records 翻页, 把每页 record_id 汇总, 然后一次并发拉所有源码
    (避免 N×page 次并发开/关 ThreadPoolExecutor)

    Parameters
    ----------
    per_page     : 每页多少 (最大 50)
    max_pages    : 最多翻多少页 (默认 50, 即 50×50=2500 条 records 上限)
    max_workers  : 并发拉源码的线程数

    Returns
    -------
    list of dict, 同 fetch_records_with_source
    """
    if not (1 <= per_page <= 50):
        raise ValueError(f"per_page 必须在 1-50, 实际 {per_page}")
    if not (1 <= max_pages <= 500):
        raise ValueError(f"max_pages 必须在 1-500, 实际 {max_pages}")

    all_records: List[Dict[str, Any]] = []
    pages_done = 0
    for p in range(1, max_pages + 1):
        try:
            page_records = fetch_records(cookies, page=p, limit=per_page)
        except Exception as e:
            logger.warning("fetch_records(page=%d) failed: %s — 停止翻页", p, e)
            break
        if not page_records:
            break  # 空页说明到底了
        all_records.extend(page_records)
        pages_done = p
        # 这一页没满 = 最后一页
        if len(page_records) < per_page:
            break

    logger.info("fetch_all_records: %d pages, %d records total",
                pages_done, len(all_records))

    if not all_records:
        return []

    # 一次性并发拉所有 record 的源码
    rids = [r.get("record_id") or r.get("id") for r in all_records]
    rids = [rid for rid in rids if rid is not None]

    out_map: Dict[Any, Dict[str, Any]] = {}

    def _fetch_one(rid):
        try:
            return rid, fetch_record_source(cookies, rid)
        except Exception as e:
            logger.warning("fetch_record_source(%s) failed: %s", rid, e)
            return rid, {"rid": rid, "sourceCode": None, "error": str(e)[:120]}

    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = [ex.submit(_fetch_one, rid) for rid in rids]
        for fut in as_completed(futures):
            rid, data = fut.result()
            out_map[rid] = data

    out: List[Dict[str, Any]] = []
    for r in all_records:
        rid = r.get("record_id") or r.get("id")
        if rid is None:
            continue
        d = out_map.get(rid, {})
        out.append({
            "rid": rid,
            "pid": r.get("pid") or d.get("pid"),
            "title": r.get("title") or d.get("title"),
            "language": d.get("language"),
            "status": d.get("status") or r.get("verdict"),
            "submitTime": d.get("submitTime") or r.get("submit_time"),
            "sourceCode": d.get("sourceCode"),
            "sourceCodeLength": d.get("sourceCodeLength"),
            "error": d.get("error"),
        })
    return out


def build_sources_zip(records_with_source: List[Dict[str, Any]]) -> BytesIO:
    """构造 zip: 每条 record 一个文件, 文件名 = {pid}_{title}.{ext}

    拿不到源码的 record 会在 zip 里写一个 .MISSING.txt 占位
    """
    buf = BytesIO()
    used_names: set[str] = set()
    missing_count = 0
    with ZipFile(buf, "w", compression=ZIP_DEFLATED) as zf:
        for r in records_with_source:
            src = r.get("sourceCode")
            fname = _source_filename(
                str(r.get("pid") or f"rid{r.get('rid')}"),
                str(r.get("title") or f"record_{r.get('rid')}"),
                r.get("language"),
            )
            # 避免重名 (同一题多次提交)
            base = fname
            n = 1
            while fname in used_names:
                n += 1
                stem, dot, ext = base.rpartition(".")
                fname = f"{stem}_{n}.{ext}" if dot else f"{base}_{n}"
            used_names.add(fname)

            if src is None:
                missing_count += 1
                zf.writestr(
                    f"_missing/{fname}.MISSING.txt",
                    f"# 该 record 的源码无法获取\n"
                    f"# rid: {r.get('rid')}\n"
                    f"# pid: {r.get('pid')}\n"
                    f"# 原因: {r.get('error') or 'unknown'}\n",
                )
            else:
                zf.writestr(fname, src)

        # README
        zf.writestr(
            "README.txt",
            f"luogu-toolkit: 洛谷源码批量下载\n"
            f"共 {len(records_with_source)} 条 record, 其中 {missing_count} 条源码缺失\n"
            f"缺失的源码会放在 _missing/ 目录下, 后缀 .MISSING.txt\n",
        )
    buf.seek(0)
    return buf


def fetch_problem(cookies: CookieDict, pid: str) -> dict:
    """拉题目详情

    Parameters
    ----------
    pid : str — 洛谷题号 (如 "P1001" / "AT_abc001_a" / "CF1A")
    """
    _require_pyluogu()
    client = _make_client(cookies)
    p = client.get_problem(pid)
    try:
        return dict(p)
    except Exception:
        return {"pid": pid}


def fetch_passed_problems(cookies: CookieDict, uid: Optional[int] = None) -> list[dict]:
    """拉已通过的题目列表 (去重, 按 AC 时间排序)

    Returns
    -------
    list[dict]: 每条含 pid / title / difficulty / tags
    """
    _require_pyluogu()
    client = _make_client(cookies)
    if uid is None:
        me = client.me()
        uid = me.uid
    # pyLuogu: get_user_practice(uid) → UserPracticeResponse
    # 实际结构 (实测):
    #   resp.data = {"passed": [...], "submitted": [...], "elo": [...], "user": {...}}
    #   resp.count = int
    # resp 本身没有 .passed / .result 字段
    try:
        resp = client.get_user_practice(uid)
    except Exception as e:
        logger.exception("get_user_practice failed")
        raise
    items = []
    if hasattr(resp, "data") and isinstance(getattr(resp, "data", None), dict):
        items = resp.data.get("passed") or []
    elif isinstance(resp, dict):
        items = (resp.get("data") or {}).get("passed") or []
    out: list[dict] = []
    seen = set()
    for p in items or []:
        # 实际字段: type / name / difficulty / pid  (没有 tags)
        if isinstance(p, dict):
            p_pid = p.get("pid")
            p_name = p.get("name")
            p_diff = p.get("difficulty")
        else:
            p_pid = getattr(p, "pid", None)
            p_name = getattr(p, "name", None)
            p_diff = getattr(p, "difficulty", None)
        if not p_pid or p_pid in seen:
            continue
        seen.add(p_pid)
        out.append({
            "pid": p_pid,
            "title": p_name,   # pyLuogu 字段叫 name, 这里对外保持叫 title 兼容旧调用方
            "difficulty": p_diff,
            "tags": [],         # pyLuogu 不返回 tags, 暂时留空
        })
    return out
