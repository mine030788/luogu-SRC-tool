# ─────────────────────────────────────────────────────────────
# luogu-toolkit · Docker 镜像
# 基础镜像: python:3.11-slim (playwright 官方推荐, 比 alpine 兼容性好)
# 大小:  ~1.2 GB (含 Chromium + ddddocr onnxruntime)
# ─────────────────────────────────────────────────────────────
FROM python:3.11-slim

# 防止 apt 缓存 + 强制 UTF-8
ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONIOENCODING=utf-8 \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8 \
    TZ=Asia/Shanghai

# 1) 系统依赖
#    - chromium 运行时依赖 (playwright install --with-deps 会装但这里先装少踩坑)
#    - libgomp1: ddddocr 的 onnxruntime 需要
#    - tzdata: 设置时区
#    - tini: 1 号进程, 正确处理 SIGTERM
RUN apt-get update && apt-get install -y --no-install-recommends \
        libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 libcups2 libdrm2 \
        libxkbcommon0 libxcomposite1 libxdamage1 libxfixes3 libxrandr2 \
        libgbm1 libpango-1.0-0 libcairo2 libasound2 libatspi2.0-0 \
        libxshmfence1 fonts-liberation fonts-noto-cjk \
        libgomp1 tzdata tini ca-certificates curl \
    && rm -rf /var/lib/apt/lists/*

# 2) 创建非 root 用户 (luogu 用户) - 安全建议
RUN groupadd -r luogu && useradd -r -g luogu -m -d /home/luogu luogu

# 3) 安装 Python 依赖
WORKDIR /app
COPY --chown=luogu:luogu pyproject.toml ./
COPY --chown=luogu:luogu luogu_toolkit ./luogu_toolkit
COPY --chown=luogu:luogu README.md LICENSE ./

# 先升级 pip 再装包 (避免老 pip 装 onnxruntime 失败)
RUN pip install --no-cache-dir --upgrade pip setuptools wheel \
    && pip install --no-cache-dir ".[full]"

# 4) 装 Playwright Chromium 浏览器
#    --with-deps 会调 apt 装系统依赖 (已在 step 1 装好, 这里跳过依赖避免重复 apt)
ENV PLAYWRIGHT_BROWSERS_PATH=/home/luogu/.cache/ms-playwright
RUN playwright install chromium \
    && chown -R luogu:luogu /home/luogu/.cache

# 5) 数据目录 (cookies.json 落盘到这里, 容器外可挂载 volume)
RUN mkdir -p /data && chown -R luogu:luogu /data
ENV LUOGU_COOKIES_PATH=/data/cookies.json

# 6) 切到非 root 用户
USER luogu
WORKDIR /home/luogu

# 7) 健康检查 (拉 / 看 200)
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -fsS http://127.0.0.1:9876/ >/dev/null || exit 1

# 8) 暴露 Web UI 端口
EXPOSE 9876

# 9) 入口: tini 1 号进程 + luogu-toolkit web
#    --host 0.0.0.0 让容器外可访问
#    --debug 关掉避免子进程翻倍
ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["luogu-toolkit", "web", "--host", "0.0.0.0", "--port", "9876"]
