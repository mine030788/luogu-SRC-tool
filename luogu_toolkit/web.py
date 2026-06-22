"""web.py - 本地 Web UI (Flask)

提供 3 个页面:
  /            入口 (选择登录方式: 密码登录 / 手动填 cookies)
  /login       密码登录 + 2FA
  /status/<sid>  登录进度查询

提供 5 个 API:
  POST /api/login/start    {username, password} → 启动登录
  GET  /api/login/status   ?sid=xxx             → 轮询状态
  POST /api/login/2fa      {sid, totp_code}     → 提交 2FA
  POST /api/login/cancel   {sid}                → 取消登录
  POST /api/cookie/save    {client_id, uid, c3vk} → 手动落盘 cookies
  GET  /api/verify                              → 校验 cookies
  GET  /api/fetch/user                           → 拉用户信息
  GET  /api/fetch/records?page=&limit=           → 拉提交记录
  GET  /api/fetch/record/<rid>                   → 拉单条 record + 源码
  GET  /api/fetch/passed                         → 拉已通过题
  GET  /api/fetch/sources?page=&limit=           → 拉所有 record + 源码 → zip 下载

默认绑定 127.0.0.1:9876, 不暴露公网。
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

logger = logging.getLogger("luogu_toolkit.web")

# Flask 可选依赖
try:
    from flask import Flask, Response, jsonify, render_template, request  # type: ignore
    _HAS_FLASK = True
except Exception:  # pragma: no cover
    Flask = None  # type: ignore
    Response = None  # type: ignore
    _HAS_FLASK = False


def _require_flask():
    if not _HAS_FLASK:
        raise RuntimeError(
            "Flask 未安装, 无法启动 Web UI。\n"
            "请运行: pip install flask>=3.0\n"
            "(或只用 CLI: luogu-toolkit login / verify / fetch)"
        )


# ═══════════════════════════════════════════════════════════════════════
#  Flask app factory
# ═══════════════════════════════════════════════════════════════════════


def create_app() -> "Flask":
    _require_flask()
    pkg_dir = Path(__file__).resolve().parent
    app = Flask(
        __name__,
        template_folder=str(pkg_dir / "templates"),
        static_folder=str(pkg_dir / "templates" / "static"),
    )
    app.secret_key = os.environ.get("LUOGU_TOOLKIT_SECRET", "luogu-toolkit-local-only")

    # ── 页面 ──

    @app.route("/")
    def index():
        return render_template("index.html")

    @app.route("/login")
    def login_page():
        return render_template("login.html")

    @app.route("/status/<sid>")
    def status_page(sid):
        return render_template("status.html", session_id=sid)

    @app.route("/data")
    def data_page():
        return render_template("data.html")

    # ── API ──

    @app.post("/api/login/start")
    def api_login_start():
        from .login import login_with_password
        username = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""
        if not username or not password:
            return jsonify({"ok": False, "error": "用户名和密码不能为空"}), 400
        result = login_with_password(username, password)
        return jsonify(result)

    @app.get("/api/login/status")
    def api_login_status():
        from .login import get_login_status
        sid = request.args.get("sid", "")
        if not sid:
            return jsonify({"ok": False, "error": "缺少 sid"}), 400
        return jsonify(get_login_status(sid))

    @app.post("/api/login/2fa")
    def api_login_2fa():
        from .login import login_with_password
        sid = (request.form.get("sid") or "").strip()
        totp = (request.form.get("totp_code") or "").strip()
        if not sid or not totp:
            return jsonify({"ok": False, "error": "缺少 sid 或 totp_code"}), 400
        result = login_with_password(session_id=sid, totp_code=totp)
        return jsonify(result)

    @app.post("/api/login/cancel")
    def api_login_cancel():
        from .login import cancel_login
        sid = (request.form.get("sid") or "").strip()
        if not sid:
            return jsonify({"ok": False, "error": "缺少 sid"}), 400
        return jsonify(cancel_login(sid))

    @app.post("/api/cookie/save")
    def api_cookie_save():
        from .cookie import build_cookie_dict, save_cookies
        try:
            cookies = build_cookie_dict(request.form.to_dict())
        except ValueError as e:
            return jsonify({"ok": False, "error": str(e)}), 400
        path = save_cookies(cookies)
        return jsonify({"ok": True, "path": str(path), "uid": cookies["_uid"]})

    @app.get("/api/verify")
    def api_verify():
        from .cookie import load_cookies
        from .fetch import verify_cookies
        try:
            c = load_cookies()
        except FileNotFoundError as e:
            return jsonify({"ok": False, "error": str(e)}), 404
        except ValueError as e:
            return jsonify({"ok": False, "error": f"cookies 文件格式错误: {e}"}), 400
        try:
            r = verify_cookies(c)
        except RuntimeError as e:
            # _pyluogu 子包不可用 (正常安装下不会发生)
            return jsonify({"ok": False, "error": str(e),
                            "fix": "pip install --force-reinstall luogu-toolkit"}), 503
        except Exception as e:
            logger.exception("verify failed")
            return jsonify({"ok": False, "error": f"校验失败: {str(e)[:200]}"}), 500
        return jsonify(r)

    # ── 数据抓取 API (让 Web UI 也能一键下载自己的数据) ──

    def _err_payload(e, hint="pip install --force-reinstall luogu-toolkit"):
        """统一错误响应: 区分 expired / forbidden / network / other"""
        from ._pyluogu.errors import AuthenticationError, ForbiddenError
        if isinstance(e, AuthenticationError):
            return jsonify({"ok": False, "error": "expired", "message": str(e)[:200]}), 401
        if isinstance(e, ForbiddenError):
            return jsonify({"ok": False, "error": "forbidden", "message": str(e)[:200]}), 403
        if isinstance(e, RuntimeError):
            return jsonify({"ok": False, "error": str(e), "fix": hint}), 503
        return jsonify({"ok": False, "error": f"抓取失败: {str(e)[:200]}"}), 500

    @app.get("/api/fetch/user")
    def api_fetch_user():
        from .cookie import load_cookies
        from .fetch import fetch_user
        try:
            c = load_cookies()
        except FileNotFoundError as e:
            return jsonify({"ok": False, "error": str(e)}), 404
        try:
            data = fetch_user(c)
        except Exception as e:
            logger.exception("fetch_user failed")
            return _err_payload(e)
        return jsonify({"ok": True, "data": data})

    @app.get("/api/fetch/records")
    def api_fetch_records():
        from .cookie import load_cookies
        from .fetch import fetch_records
        try:
            page = int(request.args.get("page", 1))
            limit = int(request.args.get("limit", 20))
        except ValueError:
            return jsonify({"ok": False, "error": "page/limit 必须是整数"}), 400
        try:
            c = load_cookies()
        except FileNotFoundError as e:
            return jsonify({"ok": False, "error": str(e)}), 404
        try:
            data = fetch_records(c, page=page, limit=limit)
        except Exception as e:
            logger.exception("fetch_records failed")
            return _err_payload(e)
        return jsonify({"ok": True, "data": data, "page": page, "limit": limit})

    @app.get("/api/fetch/passed")
    def api_fetch_passed():
        from .cookie import load_cookies
        from .fetch import fetch_passed_problems
        try:
            c = load_cookies()
        except FileNotFoundError as e:
            return jsonify({"ok": False, "error": str(e)}), 404
        try:
            data = fetch_passed_problems(c)
        except Exception as e:
            logger.exception("fetch_passed failed")
            return _err_payload(e)
        return jsonify({"ok": True, "data": data, "count": len(data)})

    @app.get("/api/fetch/record/<rid>")
    def api_fetch_record(rid):
        """拉指定 record 的源码 (调 /record/<rid>)"""
        from .cookie import load_cookies
        from .fetch import fetch_record_source
        try:
            c = load_cookies()
        except FileNotFoundError as e:
            return jsonify({"ok": False, "error": str(e)}), 404
        try:
            data = fetch_record_source(c, rid)
        except Exception as e:
            logger.exception("fetch_record_source failed (rid=%s)", rid)
            return _err_payload(e)
        return jsonify({"ok": True, "data": data})

    @app.get("/api/fetch/sources")
    def api_fetch_sources():
        """拉**所有** record + 源码, 打成 zip 流式返回

        Query: ?per_page=50&max_pages=50
               per_page  默认 50 (上限 50, 每页多少)
               max_pages 默认 50 (上限 500, 最多翻多少页 = 最多 2500 条 records)
        """
        from .cookie import load_cookies
        from .fetch import build_sources_zip, fetch_all_records_with_source
        try:
            per_page = int(request.args.get("per_page", 50))
            max_pages = int(request.args.get("max_pages", 50))
        except ValueError:
            return jsonify({"ok": False, "error": "per_page/max_pages must be int"}), 400
        if not (1 <= per_page <= 50):
            return jsonify({"ok": False, "error": "per_page 必须 1-50"}), 400
        if not (1 <= max_pages <= 500):
            return jsonify({"ok": False, "error": "max_pages 必须 1-500"}), 400
        try:
            c = load_cookies()
        except FileNotFoundError as e:
            return jsonify({"ok": False, "error": str(e)}), 404
        try:
            records = fetch_all_records_with_source(c, per_page=per_page, max_pages=max_pages)
        except Exception as e:
            logger.exception("fetch_all_records_with_source failed")
            return _err_payload(e)
        if not records:
            return jsonify({"ok": False, "error": "没有 record",
                            "message": "你账号没有任何 record (可能从未提交)"}), 404
        zip_buf = build_sources_zip(records)
        uid = str(c.get("_uid") or "user")
        filename = f"luogu_sources_{uid}_all_n{len(records)}.zip"
        logger.info("Built sources zip: %d records, filename=%s", len(records), filename)
        return Response(
            zip_buf.getvalue(),
            mimetype="application/zip",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    return app


def run_server(host: str = "127.0.0.1", port: int = 9876, debug: bool = False) -> None:
    app = create_app()
    print(f"   入口:    http://{host}:{port}/")
    print(f"   登录:    http://{host}:{port}/login")
    print(f"   提示:    关闭浏览器/终端后停止服务 (Ctrl+C 退出)")
    print()
    app.run(host=host, port=port, debug=debug, use_reloader=False)
