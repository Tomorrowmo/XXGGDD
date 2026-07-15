"""渲染独立性测试 —— OpenFOAM 切片走平台自有 vendored 代码，不依赖 SimGraph2 仓库。

纯单元部分（格式识别 / 选 python / vendored 模块可导入）无需任何外部环境；
端到端出图部分缺测试算例则跳过。
"""
import sys
from pathlib import Path

import pytest

from app.services import viz

_CASE_DIR = Path(r"D:/Git/SimGraph2/test_data/DLR_A_LTS")
_FLUENT_CAS = Path(
    r"D:/Git/XGDRSight/HYY_PerfomanceAnalysis/Case/case1/"
    r"Ma6.0-con1-0.6+0.4-hot-2nd-final.cas.h5")


def test_openfoam_detection():
    assert viz._is_openfoam("some/case.foam") is True
    assert viz._is_openfoam("some/case.cas.h5") is False


def test_openfoam_uses_base_python():
    # OpenFOAM 用当前解释器（基础环境含 VTK），不需外部 Romtek 环境
    assert viz._render_python("x/case.foam") == sys.executable


def test_openfoam_available_without_external_env(monkeypatch):
    # 即便 PostProcessTool / SimGraph2 路径不存在，OpenFOAM 渲染仍应可用（基础环境有 VTK）
    monkeypatch.setattr(viz.settings.assets, "postprocess_python", Path("/nonexistent/py.exe"))
    monkeypatch.setattr(viz.settings.assets, "simgraph2_root", Path("/nonexistent/simgraph2"))
    assert viz.available("x/case.foam") is True
    # Fluent（.cas.h5/.cas）用标准 VTK 读，基础环境即可，缺 Romtek 也可用
    assert viz.available("x/case.cas.h5") is True
    assert viz.available("x/case.cas") is True
    # 仍需 Romtek 的格式（如 CGNS）在缺环境时不可用
    assert viz.available("x/case.cgns") is False


def test_fluent_detection_and_python(monkeypatch):
    # Fluent 识别（CFF/HDF5 与传统 .cas），且不误判成 OpenFOAM
    assert viz._is_fluent("some/case.cas.h5") is True
    assert viz._is_fluent("some/case.cas") is True
    assert viz._is_fluent("some/case.cas.gz") is True
    assert viz._is_fluent("some/case.foam") is False
    assert viz._is_openfoam("some/case.cas.h5") is False
    # Fluent 用基础解释器（含 vtkFLUENTCFFReader），不走 PostProcessTool
    assert viz._render_python("x/case.cas.h5") == sys.executable


def test_fluent_loader_importable():
    pytest.importorskip("vtk")
    from app.services.render import fluent_loader
    assert hasattr(fluent_loader, "load_fluent")
    # SV_* → 规范名映射齐备
    assert fluent_loader._SV_CANONICAL["SV_T"] == "Temperature"
    assert fluent_loader._SV_CANONICAL["SV_U"] == "VelocityX"


def test_vendored_modules_importable():
    # 平台自有渲染模块可独立导入（纯 VTK，无 SimGraph2）
    vtk = pytest.importorskip("vtk")
    from app.services.render import openfoam_loader, simagent_render
    assert hasattr(openfoam_loader, "load_openfoam")
    assert hasattr(simagent_render, "render_case")


def _two_block_mb():
    """构造 {wall:球, farfield:大盒} 多块，用于测缩略图体选取。"""
    vtk = pytest.importorskip("vtk")
    sph = vtk.vtkSphereSource(); sph.SetRadius(1.0); sph.Update()
    box = vtk.vtkCubeSource(); box.SetXLength(20); box.SetYLength(20); box.SetZLength(20); box.Update()
    mb = vtk.vtkMultiBlockDataSet()
    mb.SetBlock(0, box.GetOutput()); mb.GetMetaData(0).Set(vtk.vtkCompositeDataSet.NAME(), "farfield")
    mb.SetBlock(1, sph.GetOutput()); mb.GetMetaData(1).Set(vtk.vtkCompositeDataSet.NAME(), "wall")
    return mb


def test_pick_body_prefers_named_not_farfield():
    pytest.importorskip("vtk")
    from app.services.render import simagent_render as SR
    surf = SR._pick_body_surface(SR._named_blocks(_two_block_mb()))
    assert surf is not None
    # 选中的应是 wall(球, 紧凑) 而非 farfield(大盒)
    bb = surf.GetBounds()
    assert (bb[1] - bb[0]) < 5    # 球直径 ~2，远小于盒子 20


def test_render_thumbnail_png(tmp_path):
    pytest.importorskip("vtk")
    from app.services.render import simagent_render as SR
    out = tmp_path / "thumb.png"
    assert SR.render_thumbnail(_two_block_mb(), str(out)) is True
    assert out.stat().st_size > 1000


def test_export_vtp(tmp_path):
    pytest.importorskip("vtk")
    from app.services.render import export_vtp as EV
    r = EV.export_vtp(_two_block_mb(), str(tmp_path))
    assert r["ok"] is True and r["n_points"] > 0
    assert (tmp_path / "surface.vtp").stat().st_size > 200
    assert (tmp_path / "meta.json").exists()
    import json
    meta = json.loads((tmp_path / "meta.json").read_text(encoding="utf-8"))
    assert meta["vtp_file"] == "surface.vtp" and "scalars" in meta


def test_render_turntable_frames(tmp_path):
    pytest.importorskip("vtk")
    from app.services.render import simagent_render as SR
    n = SR.render_turntable(_two_block_mb(), str(tmp_path), n_frames=8)
    assert n == 8
    frames = sorted(tmp_path.glob("turn_*.png"))
    assert len(frames) == 8
    assert all(f.stat().st_size > 500 for f in frames)


@pytest.mark.skipif(not _FLUENT_CAS.exists(), reason="Fluent 测试算例不可用")
def test_fluent_loader_reads_and_normalizes():
    # 端到端读真实 Fluent CFF/HDF5：标准 VTK 读到网格 + 规范化场名 + 丢弃无用 SV_ 场
    pytest.importorskip("vtk")
    from app.services.render import fluent_loader
    mb = fluent_loader.load_fluent(str(_FLUENT_CAS))
    assert mb.GetNumberOfBlocks() >= 1
    blk = mb.GetBlock(0)
    assert blk.GetNumberOfCells() > 0 and blk.GetNumberOfPoints() > 0
    cd = blk.GetCellData()
    names = {cd.GetArrayName(i) for i in range(cd.GetNumberOfArrays())}
    # SV_T/SV_P/SV_U 已规范化
    assert {"Temperature", "Pressure", "VelocityX"} <= names
    # 离散相等无用 SV_ 场已丢弃（不污染导出/渲染）
    assert not any((n or "").upper().startswith("SV_") for n in names)


@pytest.mark.skipif(not _FLUENT_CAS.exists(), reason="Fluent 测试算例不可用")
@pytest.mark.skipif(__import__("os").environ.get("RENDER_E2E") != "1",
                    reason="慢测（真渲染 ~50s），设 RENDER_E2E=1 开启")
def test_fluent_end_to_end_render(tmp_path, monkeypatch):
    # 真出图：Fluent .cas.h5 → 切片 + 缩略图，引擎标记 vendored-vtk-fluent，不依赖 Romtek
    monkeypatch.setattr(viz.settings, "previews_dir", tmp_path)
    monkeypatch.setattr(viz.settings.assets, "simgraph2_root", Path("/nonexistent/simgraph2"))
    res = viz.generate_previews(str(_FLUENT_CAS))
    assert res["available"], res.get("reason")
    assert res.get("engine") == "vendored-vtk-fluent"
    assert {"slice_X", "slice_Y", "slice_Z", "surf_a", "surf_b"} <= set(res["images"].keys())


@pytest.mark.skipif(not _CASE_DIR.exists(), reason="DLR 测试算例不可用")
def test_end_to_end_vendored_engine(tmp_path, monkeypatch):
    # 端到端：真出图，且引擎标记为 vendored（证明没走 SimGraph2/Romtek）
    monkeypatch.setattr(viz.settings, "previews_dir", tmp_path)
    # 断开 SimGraph2 仓库，证明 OpenFOAM 渲染不依赖它
    monkeypatch.setattr(viz.settings.assets, "simgraph2_root", Path("/nonexistent/simgraph2"))
    res = viz.generate_previews(str(_CASE_DIR), scalar="T")
    assert res["available"], res.get("reason")
    assert res.get("engine") == "vendored-vtk"
    assert {"slice_X", "slice_Y", "slice_Z"} <= set(res["images"].keys())
    for fn in res["images"].values():
        assert (Path(res["dir"]) / fn).stat().st_size > 1000
