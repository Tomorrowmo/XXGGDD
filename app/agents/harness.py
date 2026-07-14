"""Agent 安全拦截 —— 借鉴 SimGraph2/agent/harness.py。

对 agent 工具做确定性前置校验：路径白名单（防遍历）、危险命令黑名单、
物理量值域校验（防幻觉数值）。纯函数，便于测试。
"""
from __future__ import annotations

import re
from pathlib import Path

from app.settings import settings


class HarnessError(Exception):
    """被安全拦截拒绝。"""


def _allowed_roots() -> list[Path]:
    a = settings.assets
    return [Path(p).resolve() for p in (
        settings.data_dir, settings.case_dir, settings.ingest_dir,
        settings.previews_dir, a.simgraph2_root, a.simparse_pkg, a.sim_knowledge,
    )]


def is_within_allowed(path: str | Path) -> bool:
    try:
        p = Path(path).resolve()
    except Exception:
        return False
    for root in _allowed_roots():
        try:
            p.relative_to(root)
            return True
        except ValueError:
            continue
    return False


def assert_safe_path(path: str | Path) -> None:
    if not is_within_allowed(path):
        raise HarnessError(f"路径不在允许范围内（防遍历）：{path}")


# 危险命令模式（若将来加 shell 工具）
DANGEROUS_CMD_PATTERNS = [
    r"\brm\s+-rf\b", r"\bmkfs\b", r"\bdd\s+if=", r":\(\)\{", r"\bshutdown\b",
    r"\bformat\b", r">\s*/dev/sd", r"\bchmod\s+777\s+/\b",
]


def is_dangerous_command(cmd: str) -> bool:
    return any(re.search(p, cmd, re.IGNORECASE) for p in DANGEROUS_CMD_PATTERNS)


def assert_safe_command(cmd: str) -> None:
    if is_dangerous_command(cmd):
        raise HarnessError(f"危险命令被拒绝：{cmd[:80]}")


# 物理量值域（防幻觉；越界的 agent 输出应被标注）
PHYSICAL_RANGES = {
    "pressure_mpa": (0.0, 50.0),
    "temperature_k": (0.0, 5000.0),
    "mach": (0.0, 30.0),
    "thrust_kn": (0.0, 5000.0),
    "y_plus": (0.0, 5000.0),
}


def validate_physical_value(kind: str, value: float) -> bool:
    rng = PHYSICAL_RANGES.get(kind)
    if rng is None:
        return True
    return rng[0] <= value <= rng[1]
