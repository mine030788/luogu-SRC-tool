"""tests/test_cli.py - CLI smoke 测试

只测 argparse 能解析, 不测 Playwright 跑通
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from luogu_toolkit.cli import main  # noqa: E402


def test_help_exits_zero():
    """--help 应该正常打印, 退出码 0"""
    with pytest.raises(SystemExit) as e:
        main(["--help"])
    assert e.value.code == 0


def test_version_exits_zero(capsys):
    """--version 应打印 '0.1.0' 字符串, 退出码 0"""
    with pytest.raises(SystemExit) as e:
        main(["--version"])
    assert e.value.code == 0
    out = capsys.readouterr().out + capsys.readouterr().err
    assert "0.1.0" in out


def test_login_requires_user_and_password():
    """login 命令不带 --user --password 应进入交互分支并最终失败 (退出码 1)

    注: argparse 不强制 --user --password 必填, 缺参时我们走
    '请提供 --user 和 --password' 路径返回 1
    """
    import io
    from contextlib import redirect_stdout
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = main(["login"])
    assert rc == 1
    assert "请提供" in buf.getvalue()


def test_verify_without_cookies(tmp_path, monkeypatch):
    """verify 命令在 cookies 不存在时应该友好报错, 退出码 1"""
    monkeypatch.setenv("LUOGU_COOKIES_PATH", str(tmp_path / "nope.json"))
    import io
    from contextlib import redirect_stdout
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = main(["verify"])
    assert rc == 1
    assert "❌" in buf.getvalue()


def test_cookie_show_without_file(tmp_path, monkeypatch):
    monkeypatch.setenv("LUOGU_COOKIES_PATH", str(tmp_path / "nope.json"))
    import io
    from contextlib import redirect_stdout
    buf = io.StringIO()
    with redirect_stdout(buf):
        rc = main(["cookie", "show"])
    assert rc == 1
    assert "❌" in buf.getvalue()


def test_cookie_set_missing_client_id(tmp_path, monkeypatch):
    """cookie set 缺 --client-id 应被 argparse 拦截 (SystemExit 2)"""
    monkeypatch.setenv("LUOGU_COOKIES_PATH", str(tmp_path / "c.json"))
    with pytest.raises(SystemExit) as e:
        main(["cookie", "set", "--uid", "123"])
    assert e.value.code == 2  # argparse 错误退出码
