# ⚑ 移植自 SimGraph2/post_engine/algorithms/export_vtp.py（纯标准 VTK）。
"""把算例边界面导出为 surface.vtp（含点数据标量）+ meta.json，供前端 vtk.js 交互渲染。

数据源无关：给 vtkMultiBlockDataSet 即可。默认排除 internalMesh（体网格，太重），
只导边界面。前端 vtk.js 读 VTP → 真三维旋转/缩放 + 按标量上色 + 线框/透明度。
"""
import json
import os

import vtk

try:  # 子进程按 `render.export_vtp` 载入用相对；app 内按包载入亦可
    from .simagent_render import _named_blocks, _pick_body_surface
except ImportError:  # pragma: no cover
    from simagent_render import _named_blocks, _pick_body_surface  # type: ignore


# 体网格 / 远场 边界：3D 交互只关心物面（弹体/壁面），排除这些否则相机框住大盒子→一片黑
_EXCLUDE = ("internalmesh", "internal", "farfield", "freestream", "far",
            "background", "outer", "domain", "fluid", "elem")


def _excluded(name: str) -> bool:
    low = (name or "").lower()
    return any(h in low for h in _EXCLUDE)


def export_vtp(multiblock, out_dir: str, include_internal: bool = False) -> dict:
    """合并**物面**块（排除体网格/远场）→ 提取表面 → 写 surface.vtp + meta.json。"""
    os.makedirs(out_dir, exist_ok=True)

    def _named():
        out = []
        for i in range(multiblock.GetNumberOfBlocks()):
            b = multiblock.GetBlock(i)
            if b is None or b.IsA("vtkMultiBlockDataSet"):
                continue
            meta = multiblock.GetMetaData(i)
            nm = meta.Get(vtk.vtkCompositeDataSet.NAME()) if (meta and meta.Has(vtk.vtkCompositeDataSet.NAME())) else f"blk{i}"
            out.append((nm, b))
        return out

    # 合并所有边界块（排除体网格/远场，避免相机框住大盒子），提表面。
    # 内流(燃烧室)要保留全部壁面→合并；外流(弹体)排除远场后即物面。
    named = _named()
    kept = [b for nm, b in named if not (_excluded(nm) and not include_internal)]
    poly = None
    if kept:
        append = vtk.vtkAppendFilter()
        for b in kept:
            append.AddInputData(b)
        append.Update()
        geo = vtk.vtkGeometryFilter(); geo.SetInputData(append.GetOutput()); geo.Update()
        poly = geo.GetOutput()
    if poly is None or poly.GetNumberOfPoints() == 0:   # 全被排除/空 → 退回物面选取
        try:
            poly = _pick_body_surface(_named_blocks(multiblock))
        except Exception:  # noqa: BLE001
            poly = None
    if poly is None or poly.GetNumberOfPoints() == 0:
        return {"ok": False, "reason": "无可导出的物面块"}
    n_points = poly.GetNumberOfPoints()
    n_cells = poly.GetNumberOfCells()
    if n_points == 0:
        return {"ok": False, "reason": "表面提取为空"}

    # 单元数据 → 点数据（vtk.js 按点标量上色更平滑）
    c2p = vtk.vtkCellDataToPointData()
    c2p.SetInputData(poly)
    c2p.PassCellDataOn()
    c2p.Update()
    poly = c2p.GetOutput()

    scalars = []
    pd = poly.GetPointData()
    for i in range(pd.GetNumberOfArrays()):
        arr = pd.GetArray(i)
        if arr is None:
            continue
        comps = arr.GetNumberOfComponents()
        rng = arr.GetRange(-1) if comps > 1 else arr.GetRange()
        scalars.append({"name": arr.GetName(), "components": comps,
                        "min": float(rng[0]), "max": float(rng[1])})

    writer = vtk.vtkXMLPolyDataWriter()
    writer.SetFileName(os.path.join(out_dir, "surface.vtp"))
    writer.SetInputData(poly)
    writer.SetDataModeToBinary()
    writer.SetCompressorTypeToZLib()
    writer.Write()

    meta = {"vtp_file": "surface.vtp", "n_points": n_points, "n_cells": n_cells,
            "scalars": scalars}
    with open(os.path.join(out_dir, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    meta["ok"] = True
    return meta
