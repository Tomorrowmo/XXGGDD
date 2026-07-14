# ⚑ 提取自 SimGraph2/post_engine/engine.py 的 OpenFOAM 加载与扁平化逻辑（纯标准 VTK）。
"""OpenFOAM 算例 → 扁平 vtkMultiBlockDataSet（供 simagent_render 使用）。

只用标准 vtkOpenFOAMReader，不涉及 Romtek，故任意装了 VTK 的 python 都能跑。
"""
import os

import vtk


def load_openfoam(case_dir: str) -> vtk.vtkMultiBlockDataSet:
    """读 OpenFOAM 算例目录，取末时间步，扁平成带名字的顶层 multiblock。

    vtkOpenFOAMReader 需要目录内有一个 .foam 哨兵文件。
    输出块结构：{internalMesh, inlet, outlet, walls, ...}
    """
    sentinel = os.path.join(case_dir, "case.foam")
    if not os.path.exists(sentinel):
        open(sentinel, "w").close()

    reader = vtk.vtkOpenFOAMReader()
    reader.SetFileName(sentinel)
    reader.CacheMeshOn()
    reader.Update()  # 先填充 patch 列表
    # 显式打开每个 patch（EnableAllPatchArrays 单独用不可靠）
    for i in range(reader.GetNumberOfPatchArrays()):
        reader.SetPatchArrayStatus(reader.GetPatchArrayName(i), 1)
    reader.EnableAllCellArrays()
    reader.EnableAllPointArrays()
    reader.Modified()
    reader.Update()
    # 移到末时间步，预览取收敛态
    times = reader.GetTimeValues()
    if times is not None and times.GetNumberOfValues() > 0:
        reader.UpdateTimeStep(times.GetValue(times.GetNumberOfValues() - 1))
    raw = reader.GetOutput()
    if raw is None or raw.GetNumberOfBlocks() == 0:
        raise RuntimeError("vtkOpenFOAMReader 返回空数据集")
    return _flatten(raw)


def _flatten(raw: vtk.vtkMultiBlockDataSet) -> vtk.vtkMultiBlockDataSet:
    """把 {internalMesh, boundary={inlet,outlet,...}} 拍平成顶层带名块。"""
    flat = vtk.vtkMultiBlockDataSet()
    idx = 0

    def _add(block, name):
        nonlocal idx
        flat.SetBlock(idx, block)
        flat.GetMetaData(idx).Set(vtk.vtkCompositeDataSet.NAME(), name or f"block_{idx}")
        idx += 1

    for i in range(raw.GetNumberOfBlocks()):
        block = raw.GetBlock(i)
        meta = raw.GetMetaData(i)
        name = (meta.Get(vtk.vtkCompositeDataSet.NAME())
                if meta and meta.Has(vtk.vtkCompositeDataSet.NAME()) else f"block_{i}")
        if block is None:
            continue
        if block.IsA("vtkMultiBlockDataSet"):
            for j in range(block.GetNumberOfBlocks()):
                sub = block.GetBlock(j)
                sm = block.GetMetaData(j)
                sn = (sm.Get(vtk.vtkCompositeDataSet.NAME())
                      if sm and sm.Has(vtk.vtkCompositeDataSet.NAME()) else f"{name}_{j}")
                if sub is not None and not sub.IsA("vtkMultiBlockDataSet"):
                    _add(sub, sn)
        else:
            _add(block, name)
    return flat
