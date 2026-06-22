"""e2e_test.py - 端到端冒烟测试

启动 Web 服务后跑这脚本 (不启服务, 用 Flask test_client 模拟请求)
"""
import io
import sys
import os
from pathlib import Path

os.environ["PYTHONIOENCODING"] = "utf-8"
os.environ["LUOGU_COOKIES_PATH"] = str(Path(os.environ.get("TEMP", "/tmp")) / "luogu_toolkit_e2e_test.json")

# 清掉之前可能存在的 cookies 文件
Path(os.environ["LUOGU_COOKIES_PATH"]).unlink(missing_ok=True)

from luogu_toolkit.web import create_app

app = create_app()
client = app.test_client()

# 用 buffer 收集输出, 最后一次性写盘 (避免 PowerShell 控制台编码问题)
buf = io.StringIO()

PASSED = 0
FAILED = 0
FAILS = []


def check(name, cond, detail=""):
    global PASSED, FAILED
    mark = "OK  " if cond else "FAIL"
    line = f"  {mark} {name}" + (f" -- {detail}" if detail else "")
    buf.write(line + "\n")
    if cond:
        PASSED += 1
    else:
        FAILED += 1
        FAILS.append(name)


def section(title):
    buf.write("\n" + title + "\n")


buf.write("=" * 60 + "\n")
buf.write("  luogu-toolkit Web E2E smoke test\n")
buf.write("=" * 60 + "\n")

# 1. 页面路由
section("[1] page routes")
r = client.get("/")
check("GET /", r.status_code == 200, f"status={r.status_code}")
check("home has 'luogu-toolkit'", b"luogu-toolkit" in r.data)
check("home has 'data' link", b"/data" in r.data)

r = client.get("/login")
check("GET /login", r.status_code == 200)

r = client.get("/data")
check("GET /data", r.status_code == 200, f"status={r.status_code}")
check("data page has 3 cards",
      all(k in r.data for k in (b"\xe7\x94\xa8\xe6\x88\xb7\xe4\xbf\xa1\xe6\x81\xaf",  # 用户信息
                               b"\xe6\x8f\x90\xe4\xba\xa4\xe8\xae\xb0\xe5\xbd\x95",  # 提交记录
                               b"\xe5\xb7\xb2\xe9\x80\x9a\xe8\xbf\x87\xe9\xa2\x98")))  # 已通过题
check("data page has 'fetch' ref (JS builds URL)", b"fetch" in r.data)

r = client.get("/status/test-session-id-123")
check("GET /status/<sid>", r.status_code == 200)
check("status page contains sid", b"test-session-id-123" in r.data)

# 2. 校验 cookies 缺失场景
section("[2] /api/verify (no cookies)")
r = client.get("/api/verify")
j = r.get_json()
check("status=404 (no cookies)", r.status_code == 404, f"status={r.status_code}")
check("ok=False", j.get("ok") is False)
check("error mentions cookies.json", "cookies" in j.get("error", "").lower())

# 3. 手动填 cookies
section("[3] /api/cookie/save manual")
r = client.post("/api/cookie/save", data={
    "client_id": "fake_client_id_abc",
    "uid": "123456",
    "c3vk": "fake_c3vk",
})
j = r.get_json()
check("status=200", r.status_code == 200, f"status={r.status_code}, j={j}")
check("ok=True", j.get("ok") is True)
check("returns uid", j.get("uid") == "123456")
check("cookies file written", Path(j["path"]).exists())

# 4. /api/verify 现在能读到 cookies (但 pyLuogu 网络调用会失败)
section("[4] /api/verify (with cookies)")
r = client.get("/api/verify")
j = r.get_json()
check("not 500", r.status_code != 500, f"status={r.status_code}")
buf.write(f"     (ok={j.get('ok')}, error={j.get('error', '')[:50]})\n")

# 5. /api/fetch/user (pyLuogu.me() 不强制校验 auth — 公开用户数据)
section("[5] /api/fetch/user (fake cookies — public endpoint)")
r = client.get("/api/fetch/user")
j = r.get_json()
check("not 500", r.status_code != 500, f"status={r.status_code}")
check("has ok field", "ok" in j, f"j={list(j.keys())}")
# 注: pyLuogu.me() / get_user_info(uid) 不强制校验 auth, 公开的用户资料谁都能查
#      提交记录是隐私, 才需要 auth — 下面 [6] 才是真正的 401 场景

# 6. /api/fetch/records (这个端点会强制校验 auth — 假 cookies 应返 401)
section("[6] /api/fetch/records?page=1&limit=5 (fake cookies, expect 401)")
r = client.get("/api/fetch/records?page=1&limit=5")
j = r.get_json()
check("not 500", r.status_code != 500, f"status={r.status_code}")
check("401 expired", r.status_code == 401, f"status={r.status_code}")
check("error=expired", j.get("error") == "expired")

# 7. /api/fetch/passed (pyLuogu.get_user_practice() 不强制校验 — 公开 AC 题)
section("[7] /api/fetch/passed (fake cookies — public endpoint)")
r = client.get("/api/fetch/passed")
j = r.get_json()
check("not 500", r.status_code != 500, f"status={r.status_code}")
check("has ok field", "ok" in j)

# 8. 参数校验
section("[8] parameter validation")
r = client.get("/api/fetch/records?page=abc&limit=xyz")
check("page/limit non-int -> 400", r.status_code == 400, f"status={r.status_code}")
j = r.get_json()
check("error mentions 'integer'", "整数" in j.get("error", ""))

r = client.post("/api/cookie/save", data={"uid": "999"})
check("missing client_id -> 400", r.status_code == 400, f"status={r.status_code}")

# 总结
buf.write("\n")
buf.write("=" * 60 + "\n")
buf.write(f"  RESULT: {PASSED} passed, {FAILED} failed\n")
if FAILS:
    buf.write("  FAILED checks:\n")
    for n in FAILS:
        buf.write(f"    - {n}\n")
buf.write("=" * 60 + "\n")

# 写到磁盘 (utf-8) + 同步打印到 stdout
result = buf.getvalue()
out = Path(__file__).parent / "e2e_output.txt"
out.write_text(result, encoding="utf-8")
print(result, flush=True)
sys.exit(0 if FAILED == 0 else 1)
