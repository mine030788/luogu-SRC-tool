"""01_basic_login.py - 基础密码登录

展示最简的 SDK 用法: 启动登录 → 处理 2FA → 落盘 cookies
"""
from luogu_toolkit import login_with_password, save_cookies

print("🚀 启动登录...")
result = login_with_password("your_username", "your_password")

# 等待用户/OCR 完成
while result["state"] in ("started", "submitted_2fa"):
    import time
    time.sleep(1)
    from luogu_toolkit import get_login_status
    result = get_login_status(result["session_id"])

# 处理 2FA
if result["state"] == "need_2fa":
    print("🔐 账号开启了 2FA, 请输入 6 位验证码:")
    totp = input("> ").strip()
    result = login_with_password(
        session_id=result["session_id"],
        totp_code=totp,
    )

# 落盘
if result["state"] == "done":
    path = save_cookies(result["cookies"])
    print(f"✅ 登录成功! cookies 已保存到: {path}")
    print(f"   UID: {result.get('luogu_uid')}")
else:
    print(f"❌ 登录失败: {result.get('error')}")
