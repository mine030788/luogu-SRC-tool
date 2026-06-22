"""03_export_records.py - 导出最近 100 条提交到 JSON

展示: load_cookies + fetch_records + 数据清洗
"""
import json
from luogu_toolkit import load_cookies, fetch_records, verify_cookies

# 1) 读 cookies
cookies = load_cookies()  # 默认 ~/.luogu-toolkit/cookies.json

# 2) 先校验 (避免抓半天发现 cookie 失效)
v = verify_cookies(cookies)
if not v["ok"]:
    print(f"❌ cookies 失效: {v['error']} - {v.get('message')}")
    print("请先跑 01_basic_login.py 或 luogu-toolkit login")
    raise SystemExit(1)
print(f"✅ cookies 有效, UID={v['uid']} username={v.get('username')}")

# 3) 分页拉 5 页 × 20 条 = 100 条
all_records = []
for page in range(1, 6):
    print(f"  拉第 {page}/5 页...")
    batch = fetch_records(cookies, page=page, limit=20)
    all_records.extend(batch)
    if len(batch) < 20:
        break  # 没了

print(f"📦 共拉取 {len(all_records)} 条")

# 4) 简单统计
ac = sum(1 for r in all_records if r.get("verdict") == 12)
wa = sum(1 for r in all_records if r.get("verdict") == 4)
print(f"   AC: {ac}, WA: {wa}, AC 率: {ac/len(all_records)*100:.1f}%")

# 5) 落盘
out = "my_luogu_records.json"
with open(out, "w", encoding="utf-8") as f:
    json.dump(all_records, f, ensure_ascii=False, indent=2)
print(f"💾 已保存到: {out}")
