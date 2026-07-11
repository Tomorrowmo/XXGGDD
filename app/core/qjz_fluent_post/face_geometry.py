"""由 .cas.h5 构建面法向量、面积与中心。"""

from __future__ import annotations

import h5py
import numpy as np


def build_face_geometry(cas_file: str, face_global_indices):
    """
    输入：0-based 的面全局索引（可迭代）。
    返回：normals (N,3), areas (N,), centers (N,3)，法向已单位化。
    """
    with h5py.File(cas_file, "r") as f:
        coords = f["meshes/1/nodes/coords/1"][:]
        all_nn = f["meshes/1/faces/nodes/1/nnodes"][:]
        all_fn = f["meshes/1/faces/nodes/1/nodes"][:]

    offsets = np.zeros(len(all_nn) + 1, dtype=np.int64)
    np.cumsum(all_nn, out=offsets[1:])

    n = len(face_global_indices)
    normals = np.zeros((n, 3))
    areas = np.zeros(n)
    centers = np.zeros((n, 3))

    for li, gi in enumerate(face_global_indices):
        gi = int(gi)
        if gi < 0 or gi >= len(offsets) - 1:
            continue
        s = int(offsets[gi])
        e = int(offsets[gi + 1])
        if e <= s:
            continue
        nids = (all_fn[s:e].astype(np.int64) - 1)
        if nids.size == 0:
            continue
        if np.any(nids < 0) or np.any(nids >= len(coords)):
            continue
        pts = coords[nids]
        if pts.shape[0] == 0:
            continue

        centers[li] = pts.mean(axis=0)

        if pts.shape[0] < 3:
            areas[li] = 0.0
            normals[li] = 0.0
            continue

        nv = np.zeros(3)
        k = len(pts)
        for vi in range(k):
            vj = (vi + 1) % k
            nv[0] += (pts[vi, 1] - pts[vj, 1]) * (pts[vi, 2] + pts[vj, 2])
            nv[1] += (pts[vi, 2] - pts[vj, 2]) * (pts[vi, 0] + pts[vj, 0])
            nv[2] += (pts[vi, 0] - pts[vj, 0]) * (pts[vi, 1] + pts[vj, 1])
        nv *= 0.5
        area = float(np.linalg.norm(nv))
        areas[li] = area
        if area > 1e-30:
            normals[li] = nv / area
        else:
            normals[li] = 0.0

    return normals, areas, centers
