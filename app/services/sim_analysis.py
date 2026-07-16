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


def _is_fluent(case_path: str) -> bool:
    """Fluent HDF5(.cas.h5)/传统(.cas)——标准 VTK 可进程内读，故沿程面平均可支持。"""
    return str(case_path).lower().endswith((".cas.h5", ".cas.gz", ".cas"))


def x_slice_supported(case_path: str) -> bool:
    """沿程面平均是否支持该格式：OpenFOAM/Fluent 进程内；CGNS 等经 Romtek 子进程也支持。"""
    s = str(case_path).lower()
    return (_is_openfoam(case_path) or _is_fluent(case_path)
            or s.endswith((".cgns", ".cga", ".plt", ".case", ".vtu", ".vtm", ".vtk")))


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


_P_NAMES = ("p", "P", "Pressure", "pressure", "SV_P", "StaticPressure")
_T_NAMES = ("T", "Temperature", "temperature", "SV_T", "StaticTemperature")
_RHO_NAMES = ("rho", "density", "Density", "SV_DENSITY")
_MACH_NAMES = ("Mach", "mach", "Ma", "mach_number", "MachNumber")


def _compute_x_slice(mb, n_slices: int = 100, gamma: float | None = None) -> dict:
    """核心：给一个 VTK multiblock → 沿 X 薄层面平均（静压/静温/马赫/总温/总压）。

    与加载引擎无关：OpenFOAM/Fluent 进程内传入，CGNS 由 Romtek 子进程传入。
    单元数据优先，无则退点数据；已有 Mach 场则直接用，否则等熵算。
    """
    import vtk
    from vtk.util.numpy_support import vtk_to_numpy
    vol = _volume_block(mb)
    if vol is None or vol.GetNumberOfCells() == 0:
        return {"available": False, "reason": "无体网格单元"}
    cd = vol.GetCellData()
    if _cell_array(cd, *_P_NAMES) is not None:      # 单元场 → 用单元中心 x
        cc = vtk.vtkCellCenters(); cc.SetInputData(vol); cc.Update()
        cx = vtk_to_numpy(cc.GetOutput().GetPoints().GetData())[:, 0]
        data = cd
    else:                                            # 点场 → 用点 x
        cx = vtk_to_numpy(vol.GetPoints().GetData())[:, 0]
        data = vol.GetPointData()
    p_static = _cell_array(data, *_P_NAMES)
    t_static = _cell_array(data, *_T_NAMES)
    rho = _cell_array(data, *_RHO_NAMES)
    if p_static is None or t_static is None:
        return {"available": False, "reason": "缺静压/静温场（p/T）"}
    u = _cell_array(data, "U", "SV_U", "velocity")
    if u is not None and getattr(u, "ndim", 1) == 2 and u.shape[1] >= 3:
        velmag = C.velocity_magnitude(u[:, 0], u[:, 1], u[:, 2])
    else:
        vx = _cell_array(data, "VelocityX", "velocityX", "U_0", "Ux", "SV_U")
        vy = _cell_array(data, "VelocityY", "velocityY", "U_1", "Uy", "SV_V")
        vz = _cell_array(data, "VelocityZ", "velocityZ", "U_2", "Uz", "SV_W")
        if vx is not None:
            z = np.zeros_like(vx)
            velmag = C.velocity_magnitude(vx, vy if vy is not None else z, vz if vz is not None else z)
        else:
            velmag = np.zeros_like(p_static)
    if rho is None:
        try:
            from app.settings import settings
            R = settings.physics.gas_constant
        except Exception:  # noqa: BLE001 - 子进程可能加载不到 settings
            R = 287.0
        with np.errstate(divide="ignore", invalid="ignore"):
            rho = np.asarray(p_static, float) / (R * np.maximum(np.asarray(t_static, float), 1e-6))
    mach = _cell_array(data, *_MACH_NAMES)           # 有现成 Mach 场就用
    if mach is None:
        mach = C.mach_number(velmag, p_static, rho, gamma)
    t0 = C.total_temperature(t_static, mach, gamma)
    p0 = C.total_pressure(p_static, mach, gamma)
    out, pos = {}, None
    for key, arr in (("P_static", p_static), ("T_static", t_static),
                     ("Mach", mach), ("T0", t0), ("P0", p0)):
        pos, avg = A.slice_average(cx, np.asarray(arr, float), n_slices=n_slices)
        out[key] = [None if not np.isfinite(v) else round(float(v), 4) for v in avg]
    x_mm = [round(float(v) * 1000.0, 3) for v in pos]
    return {"available": True, "x_mm": x_mm, "fields": out, "n_slices": len(x_mm)}


def x_slice_openfoam(case_path: str, n_slices: int = 100, gamma: float | None = None) -> dict:
    """进程内沿程面平均（OpenFOAM/Fluent，标准 VTK 直接读）。"""
    if not (_is_openfoam(case_path) or _is_fluent(case_path)):
        return {"available": False, "reason": "该格式非进程内可算（用 x_slice 分派到子进程）"}
    try:
        from app.services.render import openfoam_loader, fluent_loader
    except Exception as e:  # noqa: BLE001
        return {"available": False, "reason": f"VTK 不可用：{e}"}
    p = Path(case_path)
    if str(p).lower().endswith(".foam"):
        p = p.parent
    try:
        mb = fluent_loader.load_fluent(str(p)) if _is_fluent(case_path) else openfoam_loader.load_openfoam(str(p))
        return _compute_x_slice(mb, n_slices, gamma)
    except Exception as e:  # noqa: BLE001
        return {"available": False, "reason": f"沿程面平均计算失败：{e}"}


def x_slice(case_path: str, n_slices: int = 100, gamma: float | None = None) -> dict:
    """分派：OpenFOAM/Fluent 进程内算；CGNS 等需 Romtek 的格式走子进程（复用渲染那套引擎载入）。"""
    if _is_openfoam(case_path) or _is_fluent(case_path):
        return x_slice_openfoam(case_path, n_slices, gamma)
    return _x_slice_subprocess(case_path, n_slices)


def _x_slice_subprocess(case_path: str, n_slices: int = 100) -> dict:
    """CGNS 等：Romtek 在子进程载入全体网格并算沿程面平均（与三维渲染同一 render_runner）。"""
    import os
    import subprocess
    from app.services import viz
    from app.settings import settings
    if not viz._env_ready(case_path):
        return {"available": False, "reason": "该格式需 Romtek 环境（PostProcessTool + SimGraph2），当前不可用"}
    runner = Path(__file__).with_name("render_runner.py")
    out = viz.preview_dir(case_path)
    env = {**os.environ, "SIMGRAPH2_ROOT": str(settings.assets.simgraph2_root)}
    try:
        proc = subprocess.run(
            [viz._render_python(case_path), str(runner), viz._render_source(case_path), str(out), f"xslice:{n_slices}"],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=360, env=env)
    except subprocess.TimeoutExpired:
        return {"available": False, "reason": "沿程面平均子进程超时"}
    res = viz._parse_last_json(proc.stdout)
    if not res or not res.get("available"):
        return {"available": False, "reason": (res or {}).get("reason") or (res or {}).get("error")
                or (proc.stderr[-160:] if proc.stderr else "子进程计算失败")}
    return res
