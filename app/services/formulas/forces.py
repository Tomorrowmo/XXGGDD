"""壁面力积分（提取自 wall_forces.compute_wall_forces）。

约定：法向 n 为**外法向**（指向流体外），故压力作用在壁面上的力方向为 -n。
面压力 p_i (Pa)、面积 A_i (m²)、面外法向 n_i（单位向量）、面黏性剪切矢量 τ_i (Pa·m²=N 或 N/m² 视数据)。
参考：连续介质力学面力积分；Fluent 壁面力约定。
"""
from __future__ import annotations

import numpy as np


def pressure_force(pressures, normals, areas) -> np.ndarray:
    """压力力 F_p = Σ_i p_i·(-n_i)·A_i，返回 (3,)。

    n_i 为外法向；压力沿 -n 作用于壁面。
    """
    p = np.asarray(pressures, float).reshape(-1)
    n = np.asarray(normals, float).reshape(-1, 3)
    a = np.asarray(areas, float).reshape(-1)
    return np.sum(p[:, None] * (-n) * a[:, None], axis=0)


def viscous_force(shear_vectors) -> np.ndarray:
    """黏性力 F_v = Σ_i τ_i（各面壁面剪切力矢量直接求和），返回 (3,)。"""
    s = np.asarray(shear_vectors, float).reshape(-1, 3)
    return s.sum(axis=0)


def total_force(pressures, normals, areas, shear_vectors=None) -> np.ndarray:
    """合力 F = F_p (+ F_v)。无剪切数据时只算压力力。"""
    fp = pressure_force(pressures, normals, areas)
    if shear_vectors is None:
        return fp
    return fp + viscous_force(shear_vectors)


def force_coefficient(force_component: float, rho_inf: float, v_inf: float,
                      ref_area: float) -> float:
    """力系数 C = F / (½·ρ∞·V∞²·A_ref)。ref_area/V∞ 非法时返回 0。"""
    denom = 0.5 * float(rho_inf) * float(v_inf) ** 2 * float(ref_area)
    if abs(denom) < 1e-30:
        return 0.0
    return float(force_component) / denom
