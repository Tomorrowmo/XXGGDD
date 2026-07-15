"""可压缩流等熵关系式（提取自 x_slice_average.build_volume_mesh）。

约定：静压 p (Pa)、静温 T (K)、密度 ρ (kg/m³)、速度大小 |V| (m/s)。
γ 默认取 settings.physics.gamma（已统一为 1.4，燃烧场可传 1.3）。
参考：Anderson《Modern Compressible Flow》Ch.3 等熵关系。
"""
from __future__ import annotations

import numpy as np

from app.settings import settings

ArrayLike = "np.ndarray | float"


def _gamma(gamma: float | None) -> float:
    return settings.physics.gamma if gamma is None else float(gamma)


def speed_of_sound(p, rho, gamma: float | None = None):
    """声速 a = sqrt(γ·p/ρ)。对完全气体等价 sqrt(γRT)。"""
    g = _gamma(gamma)
    a_sq = np.maximum(g * np.asarray(p, float) / np.maximum(np.asarray(rho, float), 1e-12), 1e-6)
    return np.sqrt(a_sq)


def mach_number(vel_mag, p, rho, gamma: float | None = None):
    """马赫数 M = |V| / a，a = sqrt(γp/ρ)。"""
    return np.asarray(vel_mag, float) / speed_of_sound(p, rho, gamma)


def total_temperature(t_static, mach, gamma: float | None = None):
    """总温 T0 = T·(1 + (γ-1)/2·M²)（等熵滞止）。"""
    g = _gamma(gamma)
    return np.asarray(t_static, float) * (1.0 + (g - 1.0) / 2.0 * np.asarray(mach, float) ** 2)


def total_pressure(p_static, mach, gamma: float | None = None):
    """总压 P0 = p·(1 + (γ-1)/2·M²)^(γ/(γ-1))（等熵滞止）。"""
    g = _gamma(gamma)
    return np.asarray(p_static, float) * (1.0 + (g - 1.0) / 2.0 * np.asarray(mach, float) ** 2) ** (g / (g - 1.0))


def dynamic_pressure(rho, vel_mag):
    """动压 q = ½·ρ·|V|²。"""
    return 0.5 * np.asarray(rho, float) * np.asarray(vel_mag, float) ** 2


def velocity_magnitude(u, v, w=None):
    """速度大小 |V| = sqrt(u²+v²+w²)。w 缺省按 0（2D）。"""
    u = np.asarray(u, float); v = np.asarray(v, float)
    w = np.zeros_like(u) if w is None else np.asarray(w, float)
    return np.sqrt(u ** 2 + v ** 2 + w ** 2)
