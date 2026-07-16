"""仿真专业分析：沿程面平均（公式库驱动）+ 概况/网格 section 提取。"""
from pathlib import Path

import numpy as np
import pytest

from app.services import sim_analysis

_CASE = Path(r"D:/Git/SimGraph2/test_data/DLR_A_LTS")
_FLUENT = Path(r"D:/Git/XGDRSight/HYY_PerfomanceAnalysis/Case/case1/"
               r"Ma6.0-con1-0.6+0.4-hot-2nd-final.cas.h5")


def test_is_openfoam():
    assert sim_analysis._is_openfoam("x/case.foam") is True
    assert sim_analysis._is_openfoam("x/case.cgns") is False


def test_x_slice_supported_formats():
    assert sim_analysis.x_slice_supported("x/case.foam") is True
    assert sim_analysis.x_slice_supported("x/a.cas.h5") is True   # Fluent 标准 VTK 进程内可读
    assert sim_analysis.x_slice_supported("x/a.cas") is True
    assert sim_analysis.x_slice_supported("x/mesh.cgns") is False  # CGNS 需 Romtek 子进程


def test_x_slice_unsupported_format():
    d = sim_analysis.x_slice_openfoam("x/mesh.cgns")
    assert d["available"] is False


@pytest.mark.skipif(not _FLUENT.exists(), reason="Fluent 测试算例不可用")
def test_x_slice_fluent_real():
    d = sim_analysis.x_slice_openfoam(str(_FLUENT), n_slices=20)
    assert d["available"] is True, d.get("reason")
    for k in ("P_static", "T_static", "Mach", "T0", "P0"):
        assert k in d["fields"] and len(d["fields"][k]) == len(d["x_mm"])
    t = np.array([v for v in d["fields"]["T_static"] if v is not None])
    assert 250 < np.nanmax(t) < 4000    # 燃烧温度合理区间


@pytest.mark.skipif(not _CASE.exists(), reason="DLR 测试算例不可用")
def test_x_slice_openfoam_real():
    d = sim_analysis.x_slice_openfoam(str(_CASE), n_slices=30)
    assert d["available"] is True, d.get("reason")
    for k in ("P_static", "T_static", "Mach", "T0", "P0"):
        assert k in d["fields"] and len(d["fields"][k]) == len(d["x_mm"])
    # 物理合理性：总温 ≥ 静温（等熵滞止，公式库）
    t = np.array([v for v in d["fields"]["T_static"] if v is not None])
    t0 = np.array([v for v in d["fields"]["T0"] if v is not None])
    assert np.all(t0 >= t - 1e-3)
    # 静温在合理燃烧区间
    assert 250 < np.nanmax(t) < 3000


def test_sim_sections_extractors():
    # 纯函数：给一份 simparse 概况样例，验证 section 提取
    from app.routers.analysis import _sim_overview, _sim_mesh, _sim_variables
    s = {"solver": "reactingFoam", "format": "openfoam", "is_transient": True,
         "turbulence": {"simulationType": "RAS", "RASModel": "kEpsilon"},
         "combustion": {"combustionModel": "EDC"},
         "mesh_cells": 3466, "mesh_points": 7109,
         "boundaries": [{"name": "wall", "type": "wall", "nFaces": 100},
                        {"name": "inletair", "type": "patch", "nFaces": 4}],
         "mesh_zones": [{"name": "internalMesh", "role": "volume", "n_cells": 3466}]}
    ov = _sim_overview(s)
    assert ov["solver"] == "reactingFoam" and ov["turbulence"] == "kEpsilon"
    assert ov["combustion"] == "EDC" and ov["transient"] is True
    m = _sim_mesh(s)
    assert m["cells"] == 3466 and m["n_boundaries"] == 2
    fields = {"variable_ranges": {"T": {"min": 292, "max": 1998, "mean": 800},
                                  "C": {"min": 0, "max": 0, "mean": 0}}}
    vs = _sim_variables(fields)
    names = [v["name"] for v in vs]
    assert "T" in names and "C" not in names   # 全零场被过滤
