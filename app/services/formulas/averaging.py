"""沿程/加权平均（提取自 x_slice_average.run_x_slice_analysis）。

薄层面平均：把域沿某轴切成 n 层，每层取落在该层内单元的字段均值 → 沿程曲线。
数据源无关：只要给单元中心坐标(该轴分量) + 字段值即可。
"""
from __future__ import annotations

import numpy as np


def slice_average(axis_coords, field, n_slices: int = 100,
                  axis_range: tuple[float, float] | None = None):
    """沿轴薄层平均。

    axis_coords: (N,) 单元中心在切片轴上的坐标；field: (N,) 对应字段值。
    返回 (positions (n_slices,), averaged (n_slices,))；空层为 nan。
    层厚 = 轴跨度 / n_slices（各单元共线时用微小厚度兜底，与原实现一致）。
    """
    x = np.asarray(axis_coords, float)
    f = np.asarray(field, float)
    valid = np.isfinite(x)
    if not np.any(valid):
        raise ValueError("无有效单元中心坐标")
    xv = x[valid]
    lo, hi = (float(xv.min()), float(xv.max())) if axis_range is None else axis_range
    span = hi - lo
    positions = np.linspace(lo, hi, n_slices) if n_slices > 1 else np.array([lo])
    half = max(abs(lo) * 1e-6, 1e-9) if span < 1e-12 else max(span / max(n_slices, 1) * 0.5, 1e-12)
    out = np.full(len(positions), np.nan)
    for i, xi in enumerate(positions):
        m = valid & (x >= xi - half) & (x <= xi + half)
        if m.any():
            seg = f[m]
            seg = seg[np.isfinite(seg)]
            if seg.size:
                out[i] = float(seg.mean())
    return positions, out


def area_weighted_average(field, areas) -> float:
    """面积加权平均 Σ(f_i·A_i)/ΣA_i（如面平均通量、面平均压力）。"""
    f = np.asarray(field, float).reshape(-1)
    a = np.asarray(areas, float).reshape(-1)
    tot = a.sum()
    if abs(tot) < 1e-30:
        return 0.0
    return float(np.sum(f * a) / tot)


def mass_weighted_average(field, mass_flux) -> float:
    """质量加权平均 Σ(f_i·ṁ_i)/Σṁ_i（如质量平均总压/总温）。"""
    f = np.asarray(field, float).reshape(-1)
    m = np.asarray(mass_flux, float).reshape(-1)
    tot = m.sum()
    if abs(tot) < 1e-30:
        return 0.0
    return float(np.sum(f * m) / tot)
