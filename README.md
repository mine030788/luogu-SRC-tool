# luogu-toolkit

> 洛谷账号工具集 · 登录 · 抓取 · 数据导出
> MIT License · 让你自己掌控自己的数据

> A non-affiliated, open-source toolkit for [Luogu](https://www.luogu.com.cn) — automated login (Playwright + captcha OCR + 2FA), cookie management, data export (user / records / problems / passed), local Web UI, Python SDK and Docker one-click deploy. **For personal learning only.** Use at your own risk; authors and contributors are not responsible for any account sanctions. MIT licensed.

## ⚠️ 免责声明 (请务必先读)

本项目 **luogu-toolkit** 是一个**非官方**的第三方开源工具，**与洛谷 (luogu.com.cn) 及其运营方没有任何关联、代理、合作或背书关系**。

- **本项目仅供个人学习、技术研究与个人数据备份使用**。任何商业用途、大规模抓取、恶意使用、绕过洛谷风控 / 反爬 / 限流措施的行为均不被允许。
- **使用本工具即表示你已阅读并同意 [洛谷用户协议](https://www.luogu.com.cn/policy)、《洛谷社区规则》及相关公示**。如两者冲突，以洛谷官方条款为准。
- **自动化登录 (Playwright) 与高频抓取可能触发洛谷的风控系统**，包括但不限于：图形验证码升级、IP 临时封禁、账号警告、**功能限制 (封号)**。**因使用本工具导致的任何账号问题、封号、数据丢失、纠纷、法律责任，均由使用者本人承担，与本项目作者及所有贡献者无关。**
- 本项目作者**不承担**任何因使用、误用、无法使用本工具而造成的直接或间接损失，包括但不限于账号被封、数据丢失、错过比赛 / 测评、声誉损失等。
- 本项目**不存储、不上传**任何用户数据；所有 cookies / 凭据只保存在你本机。详见下方 [🔒 数据安全](#-数据安全)。
- 本仓库代码按 **MIT 协议**开源 (见 [LICENSE](LICENSE))，但 MIT 协议**不构成**对使用方式的担保或背书。

**👉 一句话：你用 = 你负责，风险自担。**

如果你不同意以上任何一条，请**立即停止使用并删除本项目**。

## ✨ 它能做什么

- 🔐 **密码登录** —— Playwright 自动跑通洛谷登录页 + OCR 图形验证码 + 2FA 续接
- 📋 **手动填 cookies** —— 从浏览器 DevTools 复制 `__client_id / _uid / C3VK`, 一键落盘
- 🩺 **校验** —— 检测当前 cookies 是否还有效
- 📥 **基础数据抓取** —— 拉取用户信息 / 提交记录 / 题目详情 / 已通过题列表
- 🌐 **本地 Web UI** —— 不熟命令行的用户也可以用浏览器点点点
- 🐍 **Python SDK** —— `import luogu_toolkit` 即可在自己的脚本里集成

## 🚀 快速开始

### 1. 安装

```bash
# 基础安装 (只有登录功能)
pip install luogu-toolkit

# 完整安装 (含数据抓取 + Web UI)
pip install luogu-toolkit[full]

# 还要装 Playwright 浏览器
playwright install chromium
```

或者从源码装:

```bash
git clone https://github.com/<your-account>/luogu-toolkit.git
cd luogu-toolkit
pip install -e .[full]
playwright install chromium
```

### 2. 登录 (3 种方式, 选一个)

**方式 A: CLI 密码登录** (推荐)

```bash
luogu-toolkit login --user myname --password mypass
# 2FA 时按提示输入 6 位验证码
```

**方式 B: CLI 手动填 cookies**

1. 打开 [luogu.com.cn](https://www.luogu.com.cn) 并登录
2. F12 → Application → Cookies → 复制 3 个值
3. 填入:

```bash
luogu-toolkit cookie set --client-id "xxx" --uid "123456" --c3vk "yyy"
```

**方式 C: 本地 Web UI** (不熟命令行的用户)

```bash
luogu-toolkit web --port 9876
# 浏览器打开 http://127.0.0.1:9876
```

### 3. 校验 + 抓数据

```bash
# 校验
luogu-toolkit verify

# 拉自己的用户信息
luogu-toolkit fetch user

# 拉最近 20 条提交
luogu-toolkit fetch records --limit 20

# 拉 P1001 题目
luogu-toolkit fetch problem --pid P1001

# 拉已通过的题目列表
luogu-toolkit fetch passed
```

## 🐍 Python SDK

```python
from luogu_toolkit import (
    login_with_password, save_cookies,
    load_cookies, verify_cookies,
    fetch_user, fetch_records, fetch_passed_problems,
)

# 1) 登录
result = login_with_password("user", "pass")
if result["state"] == "need_2fa":
    totp = input("2FA code: ")
    result = login_with_password(session_id=result["session_id"], totp_code=totp)
if result["state"] == "done":
    save_cookies(result["cookies"])

# 2) 用 cookies 抓数据
cookies = load_cookies()
print(verify_cookies(cookies))
# {'ok': True, 'uid': 123456, 'username': 'myname', ...}

me = fetch_user(cookies)
records = fetch_records(cookies, limit=10)
passed = fetch_passed_problems(cookies)

# 3) 完全 SDK 化 (不落盘)
from luogu_toolkit import CookieDict
cookies: CookieDict = {"__client_id": "...", "_uid": "...", "C3VK": "..."}
me = fetch_user(cookies)
```

## 🔒 数据安全

- 本工具仅在本地 `127.0.0.1` 运行, 不暴露公网
- cookies 落盘到 `~/.luogu-toolkit/cookies.json` (仅当前用户可读)
- 本工具不向任何远程服务器上传你的账号、密码或 cookies
- 源码完全开源 (MIT), 你可以审查每一行

## ⚠️ 风险提示

- 密码登录用 Playwright 驱动浏览器, 理论上洛谷风控可能判定为 bot
- 如果你的账号被风控, 请改用 **方式 B (手动填 cookies)**
- 请勿将 `cookies.json` 上传到 git/网盘/任何公开位置 — 拿到你的 cookies 的人可以完全控制你的洛谷账号

## 🐳 Docker 部署

适合不想配 Python 环境 / 想长期后台运行 / 想在 NAS / 树莓派上跑的场景。

### 方式 A: `docker compose` (推荐)

**1) 拉取代码**

```bash
git clone https://github.com/<your-account>/luogu-toolkit.git
cd luogu-toolkit
```

**2) 启动服务**

```bash
# 后台启动 (首次会 build 镜像, 约 5-10 分钟)
docker compose up -d

# 看启动日志
docker compose logs -f
# 看到 "Running on http://0.0.0.0:9876" 就 OK 了
```

**3) 浏览器打开**

```
http://localhost:9876/
```

(若部署在远程机器, 改为 `http://<服务器IP>:9876/`)

**4) 日常操作**

```bash
docker compose down        # 停止
docker compose restart     # 重启
docker compose pull        # 拉新版本
docker compose up -d --build  # 重新 build 后启动
docker compose logs -f --tail 200  # 看最近 200 行日志
```

**5) 数据落盘位置**

`cookies.json` 持久化到 `./data/cookies.json`, 容器删除/重建后凭据不丢:

```bash
ls -la data/
# -rw-------  1 luogu luogu  256 Jun 22 03:30 cookies.json

# 备份
cp data/cookies.json data/cookies.bak.json
```

### 方式 B: 直接 `docker run` (无 compose)

```bash
# 1) build 镜像
docker build -t luogu-toolkit:0.1.0 .

# 2) 启动
docker run -d \
    --name luogu-toolkit \
    --restart unless-stopped \
    -p 9876:9876 \
    -v $(pwd)/data:/data \
    -e TZ=Asia/Shanghai \
    luogu-toolkit:0.1.0

# 3) 看日志
docker logs -f luogu-toolkit

# 4) 停止
docker stop luogu-toolkit
docker rm luogu-toolkit
```

### 方式 C: 拉预构建镜像 (镜像发布后)

```bash
docker pull ghcr.io/mine030788/luogu-toolkit:0.1.0
docker run -d -p 9876:9876 -v $(pwd)/data:/data ghcr.io/mine030788/luogu-toolkit:0.1.0
```

### Docker 常见问题

| 问题 | 解决 |
|---|---|
| `Could not find Chromium` | 在容器内跑一次 `playwright install chromium` (镜像里已装, 通常不会出) |
| 中文验证码识别乱码 | 已装 `fonts-noto-cjk`, 若还是乱码, 重新 build 一次 (`docker compose build --no-cache`) |
| 端口冲突 | 改 `docker-compose.yml` 里的 `"9876:9876"` → `"19876:9876"` |
| 想改 Web 端口 | 改 `docker-compose.yml` 的 `command` 字段, 追加 `--port 19876` |
| 想跑在 NAS/路由器 | 镜像基于 `linux/amd64` + `linux/arm64` 双架构 (buildx), 拉对应 tag 即可 |
| cookies 不持久化 | 检查 `./data/` 目录权限 (`chown -R 1000:1000 ./data`), 容器内用户是 UID 1000 |

### Docker 架构

- 基础镜像: `python:3.11-slim` (≈80 MB, 比 alpine 兼容性好)
- Chromium: Playwright 官方预编译 (≈150 MB)
- ddddocr + onnxruntime: 图形验证码 OCR (≈80 MB)
- 镜像总体积: **≈1.2 GB** (未压缩)
- 启动时间: **≈3 秒** (健康检查 15 秒后通过)
- 内存占用: **≈600 MB - 1.2 GB** (Playwright Chromium 是大头)
- 1 号进程: `tini` (正确处理 SIGTERM, 避免 Chromium 残留 zombie)

### 完整 docker-compose.yml 示例 (含反向代理 / HTTPS)

```yaml
version: "3.8"

services:
  luogu-toolkit:
    build: .
    image: luogu-toolkit:0.1.0
    container_name: luogu-toolkit
    restart: unless-stopped
    expose:
      - "9876"   # 不直接暴露, 走 caddy 反代
    volumes:
      - ./data:/data
    networks:
      - lt-net

  caddy:
    image: caddy:2-alpine
    container_name: lt-caddy
    restart: unless-stopped
    ports:
      - "443:443"
      - "80:80"
    volumes:
      - ./Caddyfile:/etc/caddy/Caddyfile:ro
      - caddy_data:/data
      - caddy_config:/config
    networks:
      - lt-net

volumes:
  caddy_data:
  caddy_config:

networks:
  lt-net:
    driver: bridge
```

配套 `Caddyfile`:

```
your-domain.com {
    reverse_proxy luogu-toolkit:9876
}
```

这样 `https://your-domain.com/` 就是带 HTTPS 的 luogu-toolkit。

## 🛠️ 故障排除

| 问题 | 解决 |
|---|---|
| `Playwright 未安装` | `playwright install chromium` |
| `ddddocr 未安装` | `pip install ddddocr` |
| `pyLuogu 未安装` | 已内嵌, 不可能发生; 看到这个就是安装损坏了, 试 `pip install --force-reinstall luogu-toolkit` |
| `Flask 未安装` | `pip install luogu-toolkit[web]` |
| OCR 连续 6 次失败 | 切到手动填 cookies |
| cookies 一直失效 | 重新登录, 洛谷 cookie 大概 7-30 天有效 |
| Docker 镜像构建失败 (网络) | 用 `docker buildx build --network=host` 或配国内镜像 |
| Docker 容器启动后立即退出 | `docker logs luogu-toolkit` 看错误 |
| `fetch_user` 返了别人的数据 | pyLuogu 的 `me()` / `get_user_info(uid)` 不强制校验 cookies, 公开数据谁都能查; 想验证有效性用 `luogu-toolkit verify` |

> **关于「公开端点 vs 隐私端点」**: 洛谷 API 设计上, 用户资料 (UID/昵称/签名/头像) 和 AC 题列表是**公开**的, 任何人带 UID 都能查; **只有**「提交记录」是隐私的, 必须登录。基于此, `fetch_user` 和 `fetch_passed_problems` 即使 cookies 是假的也可能成功 (这与「`/api/verify` 失败」并不矛盾)。需要严格校验时调用 `luogu-toolkit verify`。

## 📂 项目结构

```
luogu-toolkit/
├── luogu_toolkit/
│   ├── __init__.py     # 公共 API 导出
│   ├── __main__.py     # python -m luogu_toolkit
│   ├── cli.py          # argparse CLI
│   ├── web.py          # Flask 本地 Web UI
│   ├── cookie.py       # cookies 提取/落盘
│   ├── login.py        # 密码登录 + 2FA
│   ├── fetch.py        # 数据抓取 (pyLuogu 包装)
│   └── templates/      # Web UI HTML
├── examples/           # SDK 使用示例
├── tests/              # pytest 单元测试
├── pyproject.toml
├── requirements.txt
├── LICENSE             # MIT
└── README.md           # 本文件
```

## 📜 License

MIT — 详见 [LICENSE](LICENSE) 文件。

## 🙏 致谢

- [pyLuogu](https://github.com/NekoOS-Group/luogu-api-python) (内嵌为 `luogu_toolkit._pyluogu`) — 洛谷 API 包装
- [Playwright](https://playwright.dev/python/) — 浏览器自动化
- [ddddocr](https://github.com/sml2h3/ddddocr) — 图形验证码 OCR

## 💬 联系

- Telegram 交流群: [https://t.me/+Q4h6R9iM5F80NDEy](https://t.me/+Q4h6R9iM5F80NDEy)

---

**免责声明**: 本工具仅供学习与个人数据备份使用, 请遵守洛谷用户协议。
