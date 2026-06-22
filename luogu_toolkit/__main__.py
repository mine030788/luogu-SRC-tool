"""luogu-toolkit CLI/Web 入口

用法:
  python -m luogu_toolkit --help           # CLI 帮助
  python -m luogu_toolkit login --user x --password y
  python -m luogu_toolkit fetch records --limit 5
  python -m luogu_toolkit web --port 9876  # 启动本地 Web UI
"""
from .cli import main

if __name__ == "__main__":
    raise SystemExit(main())
