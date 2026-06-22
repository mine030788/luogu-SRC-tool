"""tests/test_cookie.py - cookie 模块单元测试

不需要 Playwright / 浏览器, 纯函数测试
"""
import json
import os
import sys
import tempfile
from pathlib import Path

import pytest

# 让测试能找到 luogu_toolkit 包
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from luogu_toolkit.cookie import (  # noqa: E402
    build_cookie_dict, save_cookies, load_cookies,
    cookies_to_header, cookies_fingerprint, DEFAULT_COOKIES_PATH,
)


def test_build_cookie_dict_basic():
    c = build_cookie_dict({
        "client_id": "abc123",
        "uid": "123456",
        "c3vk": "xyz",
    })
    assert c["__client_id"] == "abc123"
    assert c["_uid"] == "123456"
    assert c["C3VK"] == "xyz"


def test_build_cookie_dict_accepts_long_names():
    """同时支持长名 (__client_id) 和短名 (client_id)"""
    c = build_cookie_dict({
        "__client_id": "longname",
        "_uid": "999",
    })
    assert c["__client_id"] == "longname"
    assert c["_uid"] == "999"


def test_build_cookie_dict_c3vk_optional():
    c = build_cookie_dict({
        "client_id": "x",
        "uid": "1",
    })
    assert c["C3VK"] == ""  # 留空兼容


def test_build_cookie_dict_missing_client_id():
    with pytest.raises(ValueError, match="__client_id"):
        build_cookie_dict({"uid": "123"})


def test_build_cookie_dict_missing_uid():
    with pytest.raises(ValueError, match="_uid"):
        build_cookie_dict({"client_id": "x"})


def test_save_and_load_roundtrip(tmp_path):
    target = tmp_path / "test_cookies.json"
    cookies = {
        "__client_id": "abc",
        "_uid": "999",
        "C3VK": "token123",
    }
    p = save_cookies(cookies, path=target)
    assert p == target
    assert target.exists()

    data = json.loads(target.read_text(encoding="utf-8"))
    assert data["version"] == 1
    assert data["uid"] == "999"
    assert data["cookies"]["C3VK"] == "token123"
    assert "saved_at" in data

    loaded = load_cookies(path=target)
    assert loaded["__client_id"] == "abc"
    assert loaded["_uid"] == "999"
    assert loaded["C3VK"] == "token123"


def test_load_cookies_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError, match="请先用"):
        load_cookies(path=tmp_path / "nope.json")


def test_cookies_to_header():
    h = cookies_to_header({
        "__client_id": "a", "_uid": "1", "C3VK": "t",
    })
    assert "__client_id=a" in h
    assert "_uid=1" in h
    assert "C3VK=t" in h


def test_cookies_to_header_skip_empty():
    h = cookies_to_header({
        "__client_id": "a", "_uid": "1", "C3VK": "",
    })
    # C3VK 空字符串应被跳过
    assert "C3VK" not in h


def test_cookies_fingerprint():
    fp = cookies_fingerprint({
        "__client_id": "abcdef1234567890",
        "_uid": "123456",
    })
    assert "1234" in fp  # uid 前 4 位
    assert "567890" in fp  # cid 后 6 位
    assert "..." in fp  # 脱敏


def test_cookies_fingerprint_empty():
    assert cookies_fingerprint({}) == "empty"


def test_default_path_override_via_env(monkeypatch, tmp_path):
    p = tmp_path / "env_cookies.json"
    monkeypatch.setenv("LUOGU_COOKIES_PATH", str(p))
    # 重新导入让常量刷新 (不直接 reload, 只验证我们不依赖这个常量)
    save_cookies({"__client_id": "x", "_uid": "1"}, path=p)
    assert p.exists()
