"""04_passed_problems.py - 导出已通过题列表

用于备份 / 分析自己的 AC 进度
"""
import json
from luogu_toolkit import load_cookies, fetch_passed_problems, verify_cookies

cookies = load_cookies()
v = verify_cookies(cookies)
if not v["ok"]:
    print(f"❌ cookies 失效: {v['error']}")
    raise SystemExit(1)

print(f"⏳ 拉取已通过题列表 (UID={v['uid']})...")
passed = fetch_passed_problems(cookies)
print(f"📦 共 {len(passed)} 题")

# 按难度分组
by_diff = {}
for p in passed:
    diff = p.get("difficulty", 0)
    by_diff.setdefault(diff, []).append(p)
for diff, items in sorted(by_diff.items()):
    diff_name = {0: "暂无", 1: "入门", 2: "普及-", 3: "普及/提高-",
                 4: "普及+/提高", 5: "提高+/省选-", 6: "省选/NOI-",
                 7: "NOI/NOI+/CTSC"}.get(diff, f"难度{diff}")
    print(f"  难度 {diff} ({diff_name}): {len(items)} 题")

out = "my_passed_problems.json"
with open(out, "w", encoding="utf-8") as f:
    json.dump(passed, f, ensure_ascii=False, indent=2)
print(f"💾 已保存到: {out}")
