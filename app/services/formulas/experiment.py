"""试验数据公式（提取自 plotter / experiment 的大气修正）。

热试车压力传感器多为**相对压力**，绝对压力 = 相对 + 大气压（默认 0.101325 MPa，可配）。
统计量（min/max/mean/std）见 services.experiment.compute_stats（此处只放纯公式）。
"""
from __future__ import annotations

import numpy as np

from app.settings import settings


def atmos_correct(rel_pressure_mpa, correction_mpa: float | None = None):
    """相对压力(MPa) → 绝对压力(MPa)：p_abs = p_rel + p_atm。"""
    corr = settings.experiment.atmos_correction_mpa if correction_mpa is None else float(correction_mpa)
    return np.asarray(rel_pressure_mpa, float) + corr


def coefficient_of_variation(values) -> float:
    """变异系数 CV = σ/|μ|（重复性核查用）。μ≈0 返回 0。"""
    a = np.asarray(values, float).reshape(-1)
    a = a[np.isfinite(a)]
    if a.size == 0:
        return 0.0
    mu = a.mean()
    if abs(mu) < 1e-30:
        return 0.0
    return float(a.std() / abs(mu))


def relative_deviation_pct(value, truth) -> float:
    """相对偏差 (value-truth)/|truth|·100%（对比评估用）。truth=0 返回 0。"""
    if abs(float(truth)) < 1e-30:
        return 0.0
    return float((float(value) - float(truth)) / abs(float(truth)) * 100.0)
