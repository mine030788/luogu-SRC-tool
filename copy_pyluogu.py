"""copy_pyluogu.py - 把 pyLuogu 从 upstream copy 进 luogu-toolkit 子包"""
import shutil
from pathlib import Path

SRC = Path(r"C:\Users\zpy20\Desktop\项目\luoguAI\luogu-api-python\pyLuogu")
DST = Path(r"C:\Users\zpy20\Desktop\项目\luoguAI\luogu-toolkit\luogu_toolkit\_pyluogu")

# 复制时跳过的文件 (上游作者的政治立场声明等非技术内容)
# 这些文件没有任何功能作用 (def wish(): pass), 仅作签名用
SKIP_NAMES = {
    "🏳️‍⚧️.py",  # upstream pyLuogu 的 pride 旗签名文件
}

# 清空目标目录 (除了 bits/)
if DST.exists():
    shutil.rmtree(DST)
DST.mkdir(parents=True)
(DST / "bits").mkdir(parents=True)

# 复制所有 .py 文件
for f in SRC.glob("*.py"):
    if f.name in SKIP_NAMES:
        print(f"  skipped: {f.name}  (in SKIP_NAMES)")
        continue
    shutil.copy2(f, DST / f.name)
    print(f"  copied: {f.name}")

# 复制 bits/
for f in (SRC / "bits").glob("*.py"):
    if f.name in SKIP_NAMES:
        print(f"  skipped: bits/{f.name}  (in SKIP_NAMES)")
        continue
    shutil.copy2(f, DST / "bits" / f.name)
    print(f"  copied: bits/{f.name}")

print()
print("Target structure:")
for f in sorted(DST.rglob("*")):
    if f.is_file():
        print(f"  {f.relative_to(DST)}  ({f.stat().st_size} bytes)")
