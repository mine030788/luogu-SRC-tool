"""luogu-toolkit · 洛谷账号工具集 (MIT License)

提供:
  - cookie 提取 (C3VK / _uid / __client_id 三参数)
  - 密码登录 (Playwright + ddddocr + 2FA)
  - 基础数据抓取 (records / user / problem)
  - CLI 命令行 + 本地 Web UI

License: MIT
仓库: https://github.com/<your-account>/luogu-toolkit
"""

__version__ = "0.1.0"
__license__ = "MIT"

# 公共 API 顶层导出 (供 import luogu_toolkit 时直接用)
from .cookie import (
    CookieDict,
    build_cookie_dict,
    save_cookies,
    load_cookies,
    cookies_to_header,
    cookies_fingerprint,
)
from .fetch import (
    fetch_user,
    fetch_records,
    fetch_problem,
    fetch_passed_problems,
    verify_cookies,
)
from .login import (
    LoginSession,
    LoginSessionManager,
    login_with_password,
    get_login_status,
    cancel_login,
)
from .bundle import (
    BUNDLE_SCHEMA_VERSION,
    build_export_data,
    build_report_zip,
    load_export_data_from_zip,
)

__all__ = [
    "__version__",
    "CookieDict", "build_cookie_dict", "save_cookies", "load_cookies",
    "cookies_to_header", "cookies_fingerprint",
    "fetch_user", "fetch_records", "fetch_problem", "fetch_passed_problems",
    "verify_cookies",
    "LoginSession", "LoginSessionManager",
    "login_with_password", "get_login_status", "cancel_login",
    "BUNDLE_SCHEMA_VERSION", "build_export_data", "build_report_zip",
    "load_export_data_from_zip",
]
