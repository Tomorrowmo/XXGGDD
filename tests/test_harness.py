"""Agent 安全拦截测试。"""
import pytest
from app.agents.harness import (
    is_within_allowed, assert_safe_path, is_dangerous_command,
    assert_safe_command, validate_physical_value, HarnessError,
)
from app.settings import settings


def test_allowed_path():
    p = settings.case_dir / "case4" / "x.cas.h5"
    assert is_within_allowed(p)


def test_disallowed_path():
    assert not is_within_allowed("C:/Windows/System32/cmd.exe")
    assert not is_within_allowed("/etc/passwd")


def test_assert_safe_path_raises():
    with pytest.raises(HarnessError):
        assert_safe_path("/etc/shadow")


def test_dangerous_commands():
    assert is_dangerous_command("rm -rf /")
    assert is_dangerous_command("dd if=/dev/zero of=/dev/sda")
    assert not is_dangerous_command("ls -la")


def test_assert_safe_command_raises():
    with pytest.raises(HarnessError):
        assert_safe_command("shutdown now")


def test_physical_value_range():
    assert validate_physical_value("pressure_mpa", 3.2)
    assert not validate_physical_value("pressure_mpa", 999.0)
    assert validate_physical_value("mach", 6.0)
    assert validate_physical_value("unknown_kind", 1e9)  # 未知类型放行


def test_tool_guard_rejects_bad_path():
    from app.agents.tools import get_case_summary
    import json
    out = json.loads(get_case_summary.invoke({"case_path": "/etc/passwd"}))
    assert "error" in out
