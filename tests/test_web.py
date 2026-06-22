"""tests/test_web.py - Flask Web UI smoke 测试

不需要浏览器, 只测路由能响应
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


@pytest.fixture
def app():
    pytest.importorskip("flask")
    from luogu_toolkit.web import create_app
    return create_app()


@pytest.fixture
def client(app):
    return app.test_client()


def test_index_returns_200(client):
    r = client.get("/")
    assert r.status_code == 200
    assert b"luogu-toolkit" in r.data


def test_login_page_returns_200(client):
    r = client.get("/login")
    assert r.status_code == 200
    assert b"\xe5\xaf\x86\xe7\xa0\x81\xe7\x99\xbb\xe5\xbd\x95" in r.data  # 密码登录


def test_status_page_returns_200(client):
    r = client.get("/status/abc123")
    assert r.status_code == 200
    assert b"abc123" in r.data


def test_api_login_start_requires_credentials(client):
    r = client.post("/api/login/start", data={})
    assert r.status_code == 400
    j = r.get_json()
    assert j["ok"] is False
    assert "用户名" in j["error"]  # 中文字符串在 JSON 中保留


def test_api_cookie_save_validates(client):
    r = client.post("/api/cookie/save", data={"uid": "123"})
    assert r.status_code == 400
    j = r.get_json()
    assert j["ok"] is False
    assert "__client_id" in j["error"]


def test_api_cookie_save_roundtrip(client, tmp_path, monkeypatch):
    monkeypatch.setenv("LUOGU_COOKIES_PATH", str(tmp_path / "c.json"))
    r = client.post("/api/cookie/save", data={
        "client_id": "abc", "uid": "999", "c3vk": "tok",
    })
    assert r.status_code == 200
    j = r.get_json()
    assert j["ok"] is True
    assert j["uid"] == "999"
    assert Path(j["path"]).exists()


def test_api_verify_without_cookies(client, tmp_path, monkeypatch):
    monkeypatch.setenv("LUOGU_COOKIES_PATH", str(tmp_path / "nope.json"))
    r = client.get("/api/verify")
    # 当 cookies 缺失时, 接口应返回 ok=False (状态码 200, 但 JSON 标识失败)
    # 也可能返回 404, 视实现而定 — 至少 ok 必须 False
    j = r.get_json()
    assert j["ok"] is False
    assert "请先" in j.get("error", "") or "不存在" in j.get("error", "")
