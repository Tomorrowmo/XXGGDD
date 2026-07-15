"""流量与边界均值（提取自 inlet_conditions.compute_inlet_report）。

提供两种质量流量：
  - mass_flow_from_flux：Fluent 约定，对面通量 SV_FLUX 求和取负（ṁ = -Σφ）；
  - mass_flow_general：通用定义 ṁ = Σ ρ_i·(V_i·n_i)·A_i（任意求解器可用）。
"""
from __future__ import annotations

import numpy as np


def mass_flow_from_flux(face_flux, sign: float = -1.0) -> float:
    """Fluent 约定质量流量 ṁ = sign·Σ SV_FLUX（默认取负，与原 test_qjz 一致）。"""
    return float(sign * np.asarray(face_flux, float).reshape(-1).sum())


def mass_flow_general(rho, vel_vectors, normals, areas) -> float:
    """通用质量流量 ṁ = Σ ρ_i·(V_i·n_i)·A_i（n 为外法向，出流为正）。"""
    rho = np.asarray(rho, float).reshape(-1)
    v = np.asarray(vel_vectors, float).reshape(-1, 3)
    n = np.asarray(normals, float).reshape(-1, 3)
    a = np.asarray(areas, float).reshape(-1)
    vn = np.sum(v * n, axis=1)
    return float(np.sum(rho * vn * a))


def boundary_mean(values) -> float:
    """边界（面邻接单元）字段算术均值——入口静压/静温/速度均值。"""
    a = np.asarray(values, float).reshape(-1)
    a = a[np.isfinite(a)]
    return float(a.mean()) if a.size else 0.0
