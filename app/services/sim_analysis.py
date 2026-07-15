"""仿真专业分析 —— 从算例真实场数据算沿程面平均等（用 formulas 公式库，数据源无关）。

OpenFOAM：用 vendored openfoam_loader 取 VTK 单元场（基础环境 VTK 即可，进程内、无渲染）。
其它格式（需 Romtek）暂不在此路径，诚实返回 available=False。
沿程面平均的马赫/总温/总压 走 app.services.formulas（等熵关系）。
"""
from __future__ import annotations

from pathlib import Path

import numpy as np

from app.services.formulas import compressible as C
from app.services.formulas import averaging as A


def _is_openfoam(case_path: str) -> bool:
    p = Path(case_path)
    if str(p).lower().endswith(".foam"):
        return True
    if p.is_dir():
        return (p / "system" / "controlDict").exists() or bool(list(p.glob("*.foam")))
    return False


def _volume_block(mb):
    """取体网格块（internalMesh / 单元最多的 UnstructuredGrid）。"""
    import vtk
    best, best_n = None, -1
    for i in range(mb.GetNumberOfBlocks()):
        b = mb.GetBlock(i)
        if b is None or not b.IsA("vtkUnstructuredGrid"):
            continue
        meta = mb.GetMetaData(i)
        name = meta.Get(vtk.vtkCompositeDataSet.NAME()) if (meta and meta.Has(vtk.vtkCompositeDataSet.NAME())) else ""
        if "internal" in (name or "").lower():
            return b
        if b.GetNumberOfCells() > best_n:
            best, best_n = b, b.GetNumberOfCells()
    return best


def _cell_array(cell_data, *names):
    """按候选名取单元场数组（OpenFOAM 场名大小写/别名兼容）。"""
    from vtk.util.numpy_support import vtk_to_numpy
    for nm in names:
        a = cell_data.GetArray(nm)
        if a is not None:
            return vtk_to_numpy(a)
    return None


def x_slice_openfoam(case_path: str, n_slices: int = 100, gamma: float | None = None) -> dict:
    """沿 X 薄层面平均：静压/静温/马赫/总温/总压（马赫等走 formulas 等熵关系）。

    返回 {available, x_mm, fields:{P_static,T_static,Mach,T0,P0}, n_slices, reason?}。
    """
    if not _is_openfoam(case_path):
        return {"available": False, "reason": "沿程面平均目前支持 OpenFOAM；其它格式需 Romtek 场数据（可扩展）"}
    try:
        import vtk  # noqa: F401
        from vtk.util.numpy_support import vtk_to_numpy
        from app.services.render import openfoam_loader
    except Exception as e:  # noqa: BLE001
        return {"available": False, "reason": f"VTK 不可用：{e}"}
    p = Path(case_path)
    if str(p).lower().endswith(".foam"):
        p = p.parent
    try:
        mb = openfoam_loader.load_openfoam(str(p))
        vol = _volume_block(mb)
        if vol is None or vol.GetNumberOfCells() == 0:
            return {"available": False, "reason": "无体网格单元"}
        import vtk
        cc = vtk.vtkCellCenters()
        cc.SetInputData(vol)
        cc.Update()
        centers = vtk_to_numpy(cc.GetOutput().GetPoints().GetData())
        cx = centers[:, 0]

        cd = vol.GetCellData()
        p_static = _cell_array(cd, "p", "P", "SV_P")
        t_static = _cell_array(cd, "T", "SV_T")
        rho = _cell_array(cd, "rho", "density", "SV_DENSITY")
        u = _cell_array(cd, "U", "SV_U")
        if p_static is None or t_static is None:
            return {"available": False, "reason": "缺静压/静温场（p/T）"}
        # 速度大小
        if u is not None and u.ndim == 2 and u.shape[1] >= 3:
            velmag = C.velocity_magnitude(u[:, 0], u[:, 1], u[:, 2])
        else:
            velmag = np.zeros_like(p_static)
        # 密度缺省时用理想气体 ρ=p/(R·T)（可压缩 OpenFOAM 常不落 rho 场）
        if rho is None:
            from app.settings import settings
            with np.errstate(divide="ignore", invalid="ignore"):
                rho = np.asarray(p_static, float) / (settings.physics.gas_constant * np.maximum(np.asarray(t_static, float), 1e-6))
        # 马赫/总温/总压（等熵，公式库）
        mach = C.mach_number(velmag, p_static, rho, gamma)
        t0 = C.total_temperature(t_static, mach, gamma)
        p0 = C.total_pressure(p_static, mach, gamma)

        out = {}
        pos = None
        for key, data in (("P_static", p_static), ("T_static", t_static),
                          ("Mach", mach), ("T0", t0), ("P0", p0)):
            pos, avg = A.slice_average(cx, np.asarray(data, float), n_slices=n_slices)
            out[key] = [None if not np.isfinite(v) else round(float(v), 4) for v in avg]
        x_mm = [round(float(v) * 1000.0, 3) for v in pos]
        return {"available": True, "x_mm": x_mm, "fields": out, "n_slices": len(x_mm)}
    except Exception as e:  # noqa: BLE001
        return {"available": False, "reason": f"沿程面平均计算失败：{e}"}
