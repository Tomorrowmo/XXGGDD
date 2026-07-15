"""面几何：多边形面积与法向（提取自 face_geometry.build_face_geometry 的 Newell 法）。

Newell 法对任意（含非平面）多边形都给出稳定的面积与法向，无需三角化。
参考：Sunday《Area of Triangles and Polygons》；Foley《Computer Graphics》。
"""
from __future__ import annotations

import numpy as np


def polygon_area_normal(points) -> tuple[float, np.ndarray]:
    """多边形（顶点有序，(k,3)）→ (面积, 单位法向)。

    法向量 nv = ½·Σ_i cross-sum(顶点_i, 顶点_{i+1})；面积 = |nv|；单位法向 = nv/|nv|。
    退化（<3 点或零面积）返回 (0.0, 零向量)。
    """
    pts = np.asarray(points, float)
    if pts.shape[0] < 3:
        return 0.0, np.zeros(3)
    nv = np.zeros(3)
    k = len(pts)
    for i in range(k):
        j = (i + 1) % k
        nv[0] += (pts[i, 1] - pts[j, 1]) * (pts[i, 2] + pts[j, 2])
        nv[1] += (pts[i, 2] - pts[j, 2]) * (pts[i, 0] + pts[j, 0])
        nv[2] += (pts[i, 0] - pts[j, 0]) * (pts[i, 1] + pts[j, 1])
    nv *= 0.5
    area = float(np.linalg.norm(nv))
    if area <= 1e-30:
        return 0.0, np.zeros(3)
    return area, nv / area


def polygon_center(points) -> np.ndarray:
    """多边形顶点形心（简单平均，与原实现一致）。"""
    pts = np.asarray(points, float)
    if pts.shape[0] == 0:
        return np.zeros(3)
    return pts.mean(axis=0)
