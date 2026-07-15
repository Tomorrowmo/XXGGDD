# ⚑ 移植自 SimGraph2/post_engine/algorithms/export_vtp.py（纯标准 VTK）。
"""把算例边界面导出为 surface.vtp（含点数据标量）+ meta.json，供前端 vtk.js 交互渲染。

数据源无关：给 vtkMultiBlockDataSet 即可。默认排除 internalMesh（体网格，太重），
只导边界面。前端 vtk.js 读 VTP → 真三维旋转/缩放 + 按标量上色 + 线框/透明度。
"""
import json
import os

import vtk


def export_vtp(multiblock, out_dir: str, include_internal: bool = False) -> dict:
    """合并边界块 → 提取表面 → 写 surface.vtp + meta.json。返回 meta。"""
    os.makedirs(out_dir, exist_ok=True)
    append = vtk.vtkAppendFilter()
    any_block = False
    for i in range(multiblock.GetNumberOfBlocks()):
        block = multiblock.GetBlock(i)
        if block is None or block.IsA("vtkMultiBlockDataSet"):
            continue
        meta = multiblock.GetMetaData(i)
        blk = meta.Get(vtk.vtkCompositeDataSet.NAME()) if (meta and meta.Has(vtk.vtkCompositeDataSet.NAME())) else ""
        if not include_internal and (blk or "").lower() in ("internalmesh", "internal"):
            continue
        append.AddInputData(block)
        any_block = True
    if not any_block:  # 无独立边界块（如单块 CGNS）→ 全导
        for i in range(multiblock.GetNumberOfBlocks()):
            b = multiblock.GetBlock(i)
            if b is not None and not b.IsA("vtkMultiBlockDataSet"):
                append.AddInputData(b); any_block = True
    if not any_block:
        return {"ok": False, "reason": "无可导出的块"}
    append.Update()

    geo = vtk.vtkGeometryFilter()
    geo.SetInputData(append.GetOutput())
    geo.Update()
    poly = geo.GetOutput()
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
