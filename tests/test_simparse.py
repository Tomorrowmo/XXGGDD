"""simparse 解析 + sim-knowledge 判据 集成测试（真实调用）。

sim-parse 包 / 测试算例缺失则自动跳过。
"""
from pathlib import Path

import pytest

from app.services import simparse_adapter as sp
from app.services import criteria

_CASE = r"D:/Git/SimGraph2/test_data/DLR_A_LTS"
_OK = sp.available() and Path(_CASE).exists()

pytestmark = pytest.mark.skipif(not _OK, reason="sim-parse / 测试算例 不可用")


def test_qoi_real():
    q = sp.qoi(_CASE)
    assert q["available"]
    variables = {x["variable"] for x in q["qoi"]}
    assert "T_max" in variables          # 真实燃烧 QOI
    # 全部有值
    assert all(x.get("value") is not None for x in q["qoi"])


def test_convergence_real():
    c = sp.convergence(_CASE)
    assert c["available"]
    names = [str(x.get("variable", "")).lower() for x in c["convergence"]]
    assert any("converg" in n or "diverg" in n for n in names)


def test_field_stats_real():
    f = sp.field_stats(_CASE)
    assert f["available"]
    assert isinstance(f["field_stats"], dict)


def test_criteria_moat_available():
    domains = criteria.list_available_domains()
    assert "numerics" in domains and "combustion" in domains
    crit = criteria.load_domain_criteria("numerics")
    assert "intents" in crit
