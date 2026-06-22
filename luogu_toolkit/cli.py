"""cli.py - 命令行入口

子命令:
  login       密码登录 (Playwright 自动 OCR + 2FA)
  fetch       抓取数据 (records / user / problem / passed)
  verify      校验当前 cookies 是否有效
  web         启动本地 Web UI (默认 127.0.0.1:9876)

Examples
--------
  # 密码登录
  luogu-toolkit login --user myname --password mypass

  # 直接填 cookies (从浏览器 DevTools 复制)
  luogu-toolkit cookie set --client-id xxx --uid 123456

  # 校验
  luogu-toolkit verify

  # 抓自己的 user 信息
  luogu-toolkit fetch user

  # 抓最近 20 条提交
  luogu-toolkit fetch records --limit 20 --page 1

  # 抓题目
  luogu-toolkit fetch problem --pid P1001

  # 启动本地 Web UI
  luogu-toolkit web --port 9876
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path


def cmd_login(args) -> int:
    from .login import login_with_password, get_login_status
    from .cookie import save_cookies

    # 模式 1: 给定用户名密码 → 启动登录
    if args.user and args.password:
        result = login_with_password(args.user, args.password)
    else:
        print("❌ 请提供 --user 和 --password, 或使用 `luogu-toolkit cookie set` 手动填")
        return 1

    if result["state"] == "started":
        sid = result["session_id"]
        print(f"🔐 登录已启动 (session={sid[:8]}...)")
        print("⏳ 等待验证码识别 + 登录完成 (可能要 5-30 秒)...")
        # 轮询
        for _ in range(120):  # 最多 60 秒
            time.sleep(0.5)
            r = get_login_status(sid)
            state = r.get("state")
            msg = r.get("message", "")
            # 简化输出
            if state == "captcha":
                print(f"  ⌨️  验证码识别中 ({r.get('captcha_attempts', 0)}/6)...", end="\r")
            elif state == "starting":
                print(f"  🚀 {msg}...", end="\r")
            elif state == "need_2fa":
                print()
                print("🔐 账号开启了 2FA, 请输入 6 位验证码:")
                totp = input("> ").strip()
                r = login_with_password(session_id=sid, totp_code=totp)
                result = r
                break
            elif state in ("done", "failed"):
                result = r
                break
        else:
            print("❌ 登录超时 (60 秒未完成)")
            return 1

    print()
    if result["state"] == "done":
        cookies = result["cookies"]
        path = save_cookies(cookies)
        print(f"✅ 登录成功!")
        print(f"   UID: {result.get('luogu_uid')}")
        print(f"   cookies 已保存到: {path}")
        print()
        print("下一步:")
        print("   luogu-toolkit verify        # 校验 cookies")
        print("   luogu-toolkit fetch user    # 拉你的用户信息")
        print("   luogu-toolkit fetch records # 拉最近提交")
        return 0
    else:
        print(f"❌ 登录失败: {result.get('error', result.get('message', '未知错误'))}")
        return 1


def cmd_cookie_set(args) -> int:
    """从 CLI 填 cookies (用户从浏览器 DevTools 复制)"""
    from .cookie import build_cookie_dict, save_cookies

    try:
        cookies = build_cookie_dict({
            "client_id": args.client_id,
            "uid": args.uid,
            "c3vk": args.c3vk or "",
        })
    except ValueError as e:
        print(f"❌ {e}")
        return 1
    path = save_cookies(cookies)
    print(f"✅ cookies 已保存到: {path}")
    print("下一步:")
    print("   luogu-toolkit verify")
    return 0


def cmd_cookie_show(args) -> int:
    """展示当前 cookies (脱敏)"""
    from .cookie import load_cookies, cookies_fingerprint
    try:
        c = load_cookies()
    except FileNotFoundError as e:
        print(f"❌ {e}")
        return 1
    print(f"📁 当前 cookies: {cookies_fingerprint(c)}")
    print(f"   __client_id: {c['__client_id'][:20]}...")
    print(f"   _uid:        {c['_uid']}")
    print(f"   C3VK:        {(c.get('C3VK') or '')[:20]}{'...' if c.get('C3VK') and len(c['C3VK']) > 20 else ''}")
    return 0


def cmd_verify(args) -> int:
    from .cookie import load_cookies
    from .fetch import verify_cookies

    try:
        c = load_cookies()
    except FileNotFoundError as e:
        print(f"❌ {e}")
        return 1
    print("⏳ 校验中 (调 /api/user/me)...")
    r = verify_cookies(c)
    if r["ok"]:
        print(f"✅ cookies 有效!")
        print(f"   UID:      {r['uid']}")
        print(f"   username: {r.get('username')}")
        print(f"   昵称:     {r.get('name')}")
        return 0
    else:
        print(f"❌ cookies 失效: {r['error']}")
        print(f"   {r.get('message', '')}")
        print()
        print("请重新登录:")
        print("   luogu-toolkit login --user <u> --password <p>")
        return 1


def cmd_fetch(args) -> int:
    from .cookie import load_cookies
    from .fetch import (
        fetch_user, fetch_records, fetch_problem, fetch_passed_problems,
    )

    try:
        c = load_cookies()
    except FileNotFoundError as e:
        print(f"❌ {e}")
        return 1

    sub = args.subcommand
    try:
        if sub == "user":
            uid = int(args.uid) if args.uid else None
            data = fetch_user(c, uid=uid)
            print(json.dumps(data, ensure_ascii=False, indent=2))
            return 0
        elif sub == "records":
            uid = int(args.uid) if args.uid else None
            data = fetch_records(c, uid=uid, page=args.page, limit=args.limit)
            print(json.dumps(data, ensure_ascii=False, indent=2))
            return 0
        elif sub == "problem":
            if not args.pid:
                print("❌ 请提供 --pid (如 P1001)")
                return 1
            data = fetch_problem(c, args.pid)
            print(json.dumps(data, ensure_ascii=False, indent=2))
            return 0
        elif sub == "passed":
            uid = int(args.uid) if args.uid else None
            data = fetch_passed_problems(c, uid=uid)
            print(json.dumps(data, ensure_ascii=False, indent=2))
            return 0
        else:
            print(f"❌ 未知子命令: {sub}")
            return 1
    except Exception as e:
        print(f"❌ 抓取失败: {e}")
        return 1


def cmd_web(args) -> int:
    from .web import run_server
    print(f"🌐 启动本地 Web UI: http://{args.host}:{args.port}")
    run_server(host=args.host, port=args.port, debug=args.debug)
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog="luogu-toolkit",
        description="洛谷账号工具集 (MIT License) — 登录/抓取/数据导出",
    )
    parser.add_argument("--version", action="version", version="%(prog)s 0.1.0")

    sub = parser.add_subparsers(dest="command", required=True)

    # login
    p_login = sub.add_parser("login", help="密码登录 (Playwright + OCR + 2FA)")
    p_login.add_argument("--user", "-u", help="洛谷用户名 (UID 或 username)")
    p_login.add_argument("--password", "-p", help="洛谷密码")
    p_login.set_defaults(func=cmd_login)

    # cookie
    p_cookie = sub.add_parser("cookie", help="管理 cookies (手动填 / 查看)")
    p_cookie_sub = p_cookie.add_subparsers(dest="cookie_cmd", required=True)
    p_set = p_cookie_sub.add_parser("set", help="从浏览器 DevTools 复制填入")
    p_set.add_argument("--client-id", required=True, help="__client_id cookie 值")
    p_set.add_argument("--uid", required=True, help="_uid cookie 值 (数字 UID)")
    p_set.add_argument("--c3vk", default="", help="C3VK (v3.9.60+ 可留空)")
    p_set.set_defaults(func=cmd_cookie_set)
    p_show = p_cookie_sub.add_parser("show", help="查看当前 cookies (脱敏)")
    p_show.set_defaults(func=cmd_cookie_show)

    # verify
    p_verify = sub.add_parser("verify", help="校验 cookies 是否有效")
    p_verify.set_defaults(func=cmd_verify)

    # fetch
    p_fetch = sub.add_parser("fetch", help="抓取数据 (依赖 pyLuogu)")
    p_fetch_sub = p_fetch.add_subparsers(dest="subcommand", required=True)
    p_fu = p_fetch_sub.add_parser("user", help="用户信息")
    p_fu.add_argument("--uid", help="不传则查自己")
    p_fu.set_defaults(func=cmd_fetch)
    p_fr = p_fetch_sub.add_parser("records", help="提交记录分页")
    p_fr.add_argument("--uid", help="不传则查自己")
    p_fr.add_argument("--page", type=int, default=1)
    p_fr.add_argument("--limit", type=int, default=20)
    p_fr.set_defaults(func=cmd_fetch)
    p_fp = p_fetch_sub.add_parser("problem", help="题目详情")
    p_fp.add_argument("--pid", required=True, help="如 P1001 / AT_abc001_a")
    p_fp.set_defaults(func=cmd_fetch)
    p_fpass = p_fetch_sub.add_parser("passed", help="已通过的题目列表")
    p_fpass.add_argument("--uid", help="不传则查自己")
    p_fpass.set_defaults(func=cmd_fetch)

    # web
    p_web = sub.add_parser("web", help="启动本地 Web UI (127.0.0.1:9876)")
    p_web.add_argument("--host", default="127.0.0.1",
                       help="绑定地址 (Docker 部署时改为 0.0.0.0)")
    p_web.add_argument("--port", type=int, default=9876)
    p_web.add_argument("--debug", action="store_true")
    p_web.set_defaults(func=cmd_web)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
