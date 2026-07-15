"""Fluent 算例 → 带规范场名的 vtkMultiBlockDataSet（供 simagent_render 使用）。

用**标准 VTK** 读 Fluent：
  - Fluent CFF / HDF5（`.cas.h5` + 伴随 `.dat.h5`）→ vtkFLUENTCFFReader
  - Fluent 传统（`.cas` + 伴随 `.dat`）           → vtkFLUENTReader
两者都在标准 VTK 9.x 里（vtkIOFLUENTCFF / vtkIOGeometry），**不依赖 Romtek**，
故平台基础环境即可出图，与 OpenFOAM 路径一样自洽。

Fluent 的解出量以 `SV_*` 命名（SV_T/SV_P/SV_DENSITY/SV_U…），且都是**单元数据**。
本加载器把它们改名成与 CGNS/OpenFOAM 一致的规范名（Temperature/Pressure/Density/
VelocityX…），这样 simagent_render 的标量优先级正则与流线逻辑（找 VelocityX/Y/Z）
可无缝复用；未识别的场保留原名（渲染时自动排在后面）。
"""
import os

import vtk

# Fluent SV_* → 规范场名。只映射有物理意义、渲染常用的量；其余保留原名。
_SV_CANONICAL = {
    "SV_T": "Temperature",
    "SV_P": "Pressure",
    "SV_DENSITY": "Density",
    "SV_U": "VelocityX",
    "SV_V": "VelocityY",
    "SV_W": "VelocityZ",
    "SV_H": "Enthalpy",
    "SV_K": "TKE",                    # 湍动能
    "SV_MU_LAM": "LaminarViscosity",
    "SV_MU_T": "TurbulentViscosity",
    "SV_WALL_DIST": "WallDistance",
    "SV_TOT_RXN": "TotalReactionRate",
}


def _cas_path(path: str) -> str:
    """接受 `.cas.h5` / `.cas` / `.cas.gz` 或目录内文件路径，返回 case 文件路径。"""
    return path


def _is_cff(cas_path: str) -> bool:
    """Fluent CFF/HDF5：文件名以 .cas.h5 结尾（或 .h5）。"""
    low = cas_path.lower()
    return low.endswith(".cas.h5") or low.endswith(".h5")


def _make_reader(cas_path: str):
    """按格式选标准 VTK 的 Fluent 读取器。找不到读取器则抛 RuntimeError。"""
    if _is_cff(cas_path):
        try:
            from vtkmodules.vtkIOFLUENTCFF import vtkFLUENTCFFReader
        except ImportError as e:  # pragma: no cover - 取决于 VTK 构建
            raise RuntimeError(f"vtkFLUENTCFFReader 不可用（需 VTK≥9.1 的 CFF 模块）：{e}")
        return vtkFLUENTCFFReader()
    try:
        from vtkmodules.vtkIOGeometry import vtkFLUENTReader
    except ImportError as e:  # pragma: no cover
        raise RuntimeError(f"vtkFLUENTReader 不可用：{e}")
    return vtkFLUENTReader()


def _rename_fields(dataset) -> None:
    """把 SV_* 改成规范名（就地），并**丢弃未映射的 SV_* 场**。

    Fluent 会带一大堆离散相/中间量场（SV_DPMS_*、SV_BF_V、SV_PSEUDO_DT…），
    对可视化无意义却会把导出的 surface.vtp 撑到上百 MB、拖慢前端下载与渲染。
    只保留有物理意义、渲染常用的规范场。
    """
    for getter in (dataset.GetCellData, dataset.GetPointData):
        fd = getter()
        drop = []
        for i in range(fd.GetNumberOfArrays()):
            arr = fd.GetArray(i)
            if arr is None:
                continue
            nm = arr.GetName()
            if nm in _SV_CANONICAL:
                arr.SetName(_SV_CANONICAL[nm])
            elif (nm or "").upper().startswith("SV_"):
                drop.append(nm)
        for nm in drop:
            fd.RemoveArray(nm)


def load_fluent(cas_path: str, *, merge_volumes: bool = True) -> vtk.vtkMultiBlockDataSet:
    """读 Fluent 算例 → 扁平带名 multiblock，场名规范化。

    Fluent 输出多为若干**体网格 zone**（无独立物面 patch），流道内流关心整个流域，
    故默认 merge_volumes=True：把各 zone 合并成单块 "fluid"，切片贯穿全域、
    物面取全域外边界。传统外流若需分块可传 False。
    """
    cas_path = _cas_path(cas_path)
    if not os.path.exists(cas_path):
        raise RuntimeError(f"Fluent case 文件不存在：{cas_path}")

    reader = _make_reader(cas_path)
    reader.SetFileName(cas_path)
    reader.UpdateInformation()
    # 打开全部单元场（Fluent 场都在 cell data）
    try:
        for i in range(reader.GetNumberOfCellArrays()):
            reader.SetCellArrayStatus(reader.GetCellArrayName(i), 1)
    except Exception:  # noqa: BLE001 - 个别读取器无此接口
        pass
    reader.Update()
    raw = reader.GetOutput()
    if raw is None or (hasattr(raw, "GetNumberOfBlocks") and raw.GetNumberOfBlocks() == 0):
        raise RuntimeError("Fluent 读取器返回空数据集")

    # 收集叶子块（UnstructuredGrid），改名规范字段
    leaves = list(_iter_leaves(raw))
    for _, leaf in leaves:
        _rename_fields(leaf)
    if not leaves:
        raise RuntimeError("Fluent 数据集无可用网格块")

    out = vtk.vtkMultiBlockDataSet()
    if merge_volumes and len(leaves) > 1:
        append = vtk.vtkAppendFilter()
        append.MergePointsOff()          # zone 间点本就重合，关合并省内存/时间
        for _, leaf in leaves:
            append.AddInputData(leaf)
        append.Update()
        merged = append.GetOutput()
        out.SetBlock(0, merged)
        out.GetMetaData(0).Set(vtk.vtkCompositeDataSet.NAME(), "fluid")
    else:
        for idx, (name, leaf) in enumerate(leaves):
            out.SetBlock(idx, leaf)
            out.GetMetaData(idx).Set(vtk.vtkCompositeDataSet.NAME(), name or f"zone{idx}")
    return out


def _iter_leaves(mb, depth: int = 0):
    """递归产出 (name, leaf_dataset)。"""
    if mb is None:
        return
    if hasattr(mb, "GetNumberOfBlocks"):
        for i in range(mb.GetNumberOfBlocks()):
            b = mb.GetBlock(i)
            if b is None:
                continue
            meta = mb.GetMetaData(i)
            nm = (meta.Get(vtk.vtkCompositeDataSet.NAME())
                  if meta and meta.Has(vtk.vtkCompositeDataSet.NAME()) else f"zone{i}")
            if hasattr(b, "GetNumberOfBlocks"):
                yield from _iter_leaves(b, depth + 1)
            elif b.GetNumberOfPoints() > 0:
                yield nm, b
    elif mb.GetNumberOfPoints() > 0:
        yield f"zone{depth}", mb
