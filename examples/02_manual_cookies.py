"""02_manual_cookies.py - 手动填 cookies

适合不想用 Playwright 的场景。
步骤:
  1. 浏览器打开 https://www.luogu.com.cn 并登录
  2. F12 → Application → Cookies → 找 https://www.luogu.com.cn
  3. 复制 __client_id / _uid / C3VK 三个值
  4. 粘到下面三个变量, 运行脚本
"""
from luogu_toolkit import build_cookie_dict, save_cookies, verify_cookies

# ↓↓↓ 把这三个值替换成你从浏览器复制的 ↓↓↓
CLIENT_ID = "paste_from_browser_here"  # 浏览器里 __client_id 的值
UID = "123456"                          # 浏览器里 _uid 的值 (注意是字符串)
C3VK = ""                               # v3.9.60+ 可留空

cookies = build_cookie_dict({
    "client_id": CLIENT_ID,
    "uid": UID,
    "c3vk": C3VK,
})
path = save_cookies(cookies)
print(f"✅ 已保存到: {path}")

# 立即校验一下
result = verify_cookies(cookies)
print(f"   校验结果: {result}")
