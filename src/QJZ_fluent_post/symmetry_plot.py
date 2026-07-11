"""
对称面 / 中心截面云图 — Matplotlib 出图。

- symmetry：Fluent symmetry 边界
- xy：z=0 平面切割（XY 视角）
- xz：y=0 平面切割（XZ 视角）
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from pathlib import Path

import h5py
import numpy as np

from .zones import parse_zones, FLUENT_ZONE_TYPE_SYMMETRY

_GAMMA = 1.4
_RS = 287.0

FIELD_CFG = [
    ("Pressure_Pa", "jet", "Pressure (Pa)", "pressure"),
    ("Temperature_K", "hot", "Temperature (K)", "temperature"),
    ("Mach_Number", "rainbow", "Mach Number", "mach"),
]

SECTION_CFG = [
    {"key": "symmetry", "label": "对称面", "kind": "symmetry"},
    {"key": "xy", "label": "XY (z=0)", "kind": "plane", "fixed_axis": 2, "fixed_val": 0.0, "u_ax": 0, "v_ax": 1, "labels": ["X", "Y"]},
    {"key": "xz", "label": "XZ (y=0)", "kind": "plane", "fixed_axis": 1, "fixed_val": 0.0, "u_ax": 0, "v_ax": 2, "labels": ["X", "Z"]},
]

VALID_SECTIONS = frozenset(s["key"] for s in SECTION_CFG)


@dataclass
class _SectionMesh:
    """截面面片网格（纯 numpy）。"""

    points: np.ndarray | None = None
    face_node_ids: list[np.ndarray] = field(default_factory=list)
    polys_2d: list[np.ndarray] = field(default_factory=list)
    polys_3d: list[np.ndarray] = field(default_factory=list)
    cell_data: dict[str, np.ndarray] = field(default_factory=dict)
    u_ax: int | None = None
    v_ax: int | None = None
    axis_labels: list[str] | None = None

    @property
    def n_cells(self) -> int:
        if self.polys_2d:
            return len(self.polys_2d)
        return len(self.face_node_ids)


def _face_unit_normal(verts: np.ndarray) -> np.ndarray:
    if verts.shape[0] < 3:
        return np.array([0.0, 0.0, 1.0])
    e0 = verts[1] - verts[0]
    e1 = verts[2] - verts[0]
    n = np.cross(e0, e1)
    if verts.shape[0] >= 4:
        e2 = verts[3] - verts[0]
        n = n + np.cross(e1, e2)
    norm = float(np.linalg.norm(n))
    if norm < 1e-12:
        return np.array([0.0, 0.0, 1.0])
    return n / norm


def _symmetry_plot_axes(mesh: _SectionMesh) -> tuple[int, int, list[str]]:
    pts = mesh.points
    accum = np.zeros(3, dtype=float)
    for nids in mesh.face_node_ids:
        accum += _face_unit_normal(pts[nids])
    n_norm = float(np.linalg.norm(accum))
    if n_norm < 1e-12:
        return 0, 1, ["X", "Y"]
    n = accum / n_norm
    thick = int(np.argmax(np.abs(n)))
    axes = [i for i in range(3) if i != thick]
    u_ax, v_ax = axes[0], axes[1]
    labels = ["X", "Y", "Z"]
    return u_ax, v_ax, [labels[u_ax], labels[v_ax]]


def _mesh_polys_2d(mesh: _SectionMesh) -> tuple[list[np.ndarray], list[str]]:
    if mesh.polys_2d:
        return mesh.polys_2d, mesh.axis_labels or ["X", "Y"]
    if mesh.u_ax is not None and mesh.v_ax is not None:
        u_ax, v_ax = mesh.u_ax, mesh.v_ax
        labels = mesh.axis_labels or ["X", "Y", "Z"]
    else:
        u_ax, v_ax, labels = _symmetry_plot_axes(mesh)
    pts = mesh.points
    polys = [pts[nids][:, [u_ax, v_ax]].astype(float) for nids in mesh.face_node_ids]
    return polys, labels[:2]


def _dedupe_points(pts: list[np.ndarray], tol: float = 1e-9) -> list[np.ndarray]:
    out: list[np.ndarray] = []
    for p in pts:
        if not any(float(np.linalg.norm(p - q)) < tol for q in out):
            out.append(p.copy())
    return out


def _order_polygon_uv(pts3d: np.ndarray, u_ax: int, v_ax: int) -> np.ndarray:
    uv = pts3d[:, [u_ax, v_ax]].astype(float)
    c = uv.mean(axis=0)
    ang = np.arctan2(uv[:, 1] - c[1], uv[:, 0] - c[0])
    return pts3d[np.argsort(ang)]


def _finite_minmax(arr: np.ndarray, default: tuple[float, float] = (0.0, 1.0)) -> tuple[float, float]:
    """对空数组 / 全非有限值安全求 min/max。"""
    a = np.asarray(arr, dtype=float).ravel()
    a = a[np.isfinite(a)]
    if a.size == 0:
        return default
    lo, hi = float(a.min()), float(a.max())
    if lo >= hi:
        hi = lo + 1.0
    return lo, hi


def _poly_uv_bounds(polys: list[np.ndarray]) -> tuple[float, float, float, float]:
    if not polys:
        raise ValueError("截面多边形为空，无法出图")
    xs = np.concatenate([p[:, 0] for p in polys if p.size > 0])
    ys = np.concatenate([p[:, 1] for p in polys if p.size > 0])
    if xs.size == 0 or ys.size == 0:
        raise ValueError("截面多边形无有效顶点，无法出图")
    xlo, xhi = _finite_minmax(xs, (0.0, 1.0))
    ylo, yhi = _finite_minmax(ys, (0.0, 1.0))
    pad_x = max((xhi - xlo) * 0.02, 1e-9)
    pad_y = max((yhi - ylo) * 0.02, 1e-9)
    return xlo - pad_x, xhi + pad_x, ylo - pad_y, yhi + pad_y


def _intersect_face_plane(
    pts: np.ndarray,
    axis: int,
    value: float,
    u_ax: int,
    v_ax: int,
    eps: float = 1e-10,
) -> np.ndarray | None:
    k = pts.shape[0]
    collected: list[np.ndarray] = []
    for i in range(k):
        a = pts[i]
        b = pts[(i + 1) % k]
        da = float(a[axis] - value)
        db = float(b[axis] - value)
        if abs(da) <= eps:
            collected.append(a.copy())
        if abs(db) <= eps and float(np.linalg.norm(b - a)) > eps:
            collected.append(b.copy())
        if (da > eps and db < -eps) or (da < -eps and db > eps):
            t = da / (da - db)
            collected.append(a + t * (b - a))
    uniq = _dedupe_points(collected, eps)
    if len(uniq) < 3:
        return None
    poly = np.stack(uniq, axis=0)
    return _order_polygon_uv(poly, u_ax, v_ax)


def _plot_section_matplotlib(mesh: _SectionMesh, scalar: str, cmap: str, title: str, out_path: str) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.colors as mcolors
    import matplotlib.pyplot as plt
    from matplotlib import cm
    from matplotlib.collections import PolyCollection

    vals = np.asarray(mesh.cell_data[scalar], dtype=float)
    if vals.size != mesh.n_cells:
        raise ValueError(f"标量 {scalar} 长度与面单元数不一致")

    polys, axis_labels = _mesh_polys_2d(mesh)
    if not polys:
        raise ValueError("截面网格无面片，无法出图")

    finite_vals = vals[np.isfinite(vals)]
    if finite_vals.size == 0:
        raise ValueError(f"标量 {scalar} 无有效数据")
    vmin, vmax = _finite_minmax(finite_vals, (0.0, 1.0))

    fig, ax = plt.subplots(figsize=(12.8, 7.2))
    norm = mcolors.Normalize(vmin=vmin, vmax=vmax)
    cmap_obj = cm.get_cmap(cmap)
    pc = PolyCollection(
        polys, array=vals, cmap=cmap_obj, norm=norm, edgecolors="none", antialiased=True,
    )
    ax.add_collection(pc)
    xlo, xhi, ylo, yhi = _poly_uv_bounds(polys)
    ax.set_xlim(xlo, xhi)
    ax.set_ylim(ylo, yhi)
    ax.set_aspect("equal", adjustable="box")
    ax.set_xlabel(f"{axis_labels[0]} / m")
    ax.set_ylabel(f"{axis_labels[1]} / m")
    ax.set_title(title)
    ax.grid(True, alpha=0.25)
    fig.colorbar(cm.ScalarMappable(norm=norm, cmap=cmap_obj), ax=ax, fraction=0.046, pad=0.04, label=title)
    fig.tight_layout()
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=150, bbox_inches="tight")
    plt.close(fig)


def _cell_scalars(
    cids: np.ndarray,
    cell_p: np.ndarray,
    cell_t: np.ndarray,
    cell_u: np.ndarray,
    cell_v: np.ndarray,
    cell_w: np.ndarray,
) -> dict[str, np.ndarray]:
    p = cell_p[cids]
    t = cell_t[cids]
    u, v, w = cell_u[cids], cell_v[cids], cell_w[cids]
    a = np.sqrt(np.maximum(_GAMMA * _RS * t, 1e-10))
    mach = np.sqrt(u**2 + v**2 + w**2) / a
    return {"Pressure_Pa": p, "Temperature_K": t, "Mach_Number": mach}


def _load_case_arrays(cas_file: str, dat_file: str):
    with h5py.File(cas_file, "r") as f:
        coords = f["meshes/1/nodes/coords/1"][:]
        all_nn = f["meshes/1/faces/nodes/1/nnodes"][:]
        all_fn = f["meshes/1/faces/nodes/1/nodes"][:]
        c0_all = f["meshes/1/faces/c0/1"][:]
    offsets = np.zeros(len(all_nn) + 1, dtype=np.int64)
    np.cumsum(all_nn, out=offsets[1:])
    with h5py.File(dat_file, "r") as fd:
        cell_t = fd["results/1/phase-1/cells/SV_T/1"][:]
        cell_u = fd["results/1/phase-1/cells/SV_U/1"][:]
        cell_v = fd["results/1/phase-1/cells/SV_V/1"][:]
        cell_w = fd["results/1/phase-1/cells/SV_W/1"][:]
        cell_p = fd["results/1/phase-1/cells/SV_P/1"][:]
    return coords, all_fn, offsets, c0_all, cell_p, cell_t, cell_u, cell_v, cell_w


def _build_symmetry_mesh(
    cas_file: str,
    coords: np.ndarray,
    all_fn: np.ndarray,
    offsets: np.ndarray,
    c0_all: np.ndarray,
    cell_p: np.ndarray,
    cell_t: np.ndarray,
    cell_u: np.ndarray,
    cell_v: np.ndarray,
    cell_w: np.ndarray,
) -> _SectionMesh | None:
    zones = parse_zones(cas_file)
    sym_zones = [z for z in zones if z["type"] == FLUENT_ZONE_TYPE_SYMMETRY]
    print(f"\nSymmetry zones: {[z['name'] for z in sym_zones]}")
    if not sym_zones:
        print("未找到 symmetry 类型边界，跳过对称面。")
        return None

    face_node_ids: list[np.ndarray] = []
    sym_gfi: list[int] = []
    for z in sym_zones:
        for gi in range(z["min_fid"] - 1, z["max_fid"]):
            sym_gfi.append(gi)
            s, e = offsets[gi], offsets[gi + 1]
            face_node_ids.append((all_fn[s:e] - 1).astype(np.int64))

    cids = c0_all[np.asarray(sym_gfi, dtype=np.int64)].astype(np.int64) - 1
    mesh = _SectionMesh(points=coords, face_node_ids=face_node_ids)
    mesh.cell_data = _cell_scalars(cids, cell_p, cell_t, cell_u, cell_v, cell_w)
    return mesh


def _build_plane_cut_meshes(
    coords: np.ndarray,
    all_fn: np.ndarray,
    offsets: np.ndarray,
    c0_all: np.ndarray,
    cell_p: np.ndarray,
    cell_t: np.ndarray,
    cell_u: np.ndarray,
    cell_v: np.ndarray,
    cell_w: np.ndarray,
    plane_specs: list[dict],
) -> dict[str, _SectionMesh | None]:
    """一次遍历全部面，同时计算多个切割平面（如 xy、xz）。"""
    if not plane_specs:
        return {}

    n_faces = len(offsets) - 1
    eps = 1e-10
    acc: dict[str, dict] = {
        spec["key"]: {"polys_2d": [], "polys_3d": [], "face_gfi": []} for spec in plane_specs
    }
    labels = ", ".join(
        f"{['X', 'Y', 'Z'][int(s['fixed_axis'])]}={float(s['fixed_val']):g}" for s in plane_specs
    )
    print(f"\n切割平面（合并遍历）: {labels}，共 {n_faces} 个面...")

    for gi in range(n_faces):
        s, e = int(offsets[gi]), int(offsets[gi + 1])
        nids = (all_fn[s:e] - 1).astype(np.int64)
        pts = coords[nids]

        for spec in plane_specs:
            fixed_axis = int(spec["fixed_axis"])
            fixed_val = float(spec["fixed_val"])
            lo = float(pts[:, fixed_axis].min())
            hi = float(pts[:, fixed_axis].max())
            if lo > fixed_val + eps or hi < fixed_val - eps:
                continue
            u_ax, v_ax = int(spec["u_ax"]), int(spec["v_ax"])
            poly3 = _intersect_face_plane(pts, fixed_axis, fixed_val, u_ax, v_ax, eps)
            if poly3 is None:
                continue
            acc[spec["key"]]["polys_3d"].append(poly3.astype(float))
            acc[spec["key"]]["polys_2d"].append(poly3[:, [u_ax, v_ax]].astype(float))
            acc[spec["key"]]["face_gfi"].append(gi)

    out: dict[str, _SectionMesh | None] = {}
    for spec in plane_specs:
        key = spec["key"]
        polys_2d = acc[key]["polys_2d"]
        polys_3d = acc[key]["polys_3d"]
        if not polys_2d:
            axis_name = ["X", "Y", "Z"][int(spec["fixed_axis"])]
            print(f"平面 {axis_name}={float(spec['fixed_val']):g} 未切到任何面。")
            out[key] = None
            continue
        gfi = np.asarray(acc[key]["face_gfi"], dtype=np.int64)
        cids = c0_all[gfi].astype(np.int64) - 1
        mesh = _SectionMesh(
            polys_2d=polys_2d,
            polys_3d=polys_3d,
            u_ax=int(spec["u_ax"]),
            v_ax=int(spec["v_ax"]),
            axis_labels=list(spec["labels"]),
        )
        mesh.cell_data = _cell_scalars(cids, cell_p, cell_t, cell_u, cell_v, cell_w)
        print(f"  {spec['label']}: 切割面片数 {mesh.n_cells}")
        out[key] = mesh
    return out


def _section_filename(section_key: str, field_tag: str) -> str:
    if section_key == "symmetry":
        return f"symmetry_{field_tag}.png"
    return f"section_{section_key}_{field_tag}.png"


def section_image_meta() -> list[dict]:
    out: list[dict] = []
    for spec in SECTION_CFG:
        images = [
            {"key": tag, "filename": _section_filename(spec["key"], tag), "title": title}
            for _, _, title, tag in FIELD_CFG
        ]
        out.append({"key": spec["key"], "label": spec["label"], "images": images})
    return out


def plot_symmetry(
    cas_file: str,
    dat_file: str,
    output_dir: str,
    *,
    sections: list[str] | None = None,
) -> dict:
    """
    生成指定截面云图（默认全部），保存 PNG 到 output_dir。
    sections: symmetry / xy / xz 的子集。
    """
    wanted = set(sections) if sections else set(VALID_SECTIONS)
    unknown = wanted - VALID_SECTIONS
    if unknown:
        raise ValueError(f"未知截面: {sorted(unknown)}")

    t_all = time.perf_counter()
    os.makedirs(output_dir, exist_ok=True)

    t0 = time.perf_counter()
    coords, all_fn, offsets, c0_all, cell_p, cell_t, cell_u, cell_v, cell_w = _load_case_arrays(cas_file, dat_file)
    print(f"  HDF5 加载: {time.perf_counter() - t0:.1f}s")

    results: dict = {}
    plane_specs = [s for s in SECTION_CFG if s["kind"] == "plane" and s["key"] in wanted]
    plane_meshes: dict[str, _SectionMesh | None] = {}
    if plane_specs:
        t0 = time.perf_counter()
        plane_meshes = _build_plane_cut_meshes(
            coords, all_fn, offsets, c0_all,
            cell_p, cell_t, cell_u, cell_v, cell_w,
            plane_specs,
        )
        print(f"  平面切割: {time.perf_counter() - t0:.1f}s")

    t_render = time.perf_counter()
    for spec in SECTION_CFG:
        key = spec["key"]
        if key not in wanted:
            continue
        if spec["kind"] == "symmetry":
            t_sym = time.perf_counter()
            mesh = _build_symmetry_mesh(
                cas_file, coords, all_fn, offsets, c0_all,
                cell_p, cell_t, cell_u, cell_v, cell_w,
            )
            print(f"  对称面网格: {time.perf_counter() - t_sym:.1f}s")
        else:
            mesh = plane_meshes.get(key)
        if mesh is None:
            continue
        for scalar, cmap, title, fname in FIELD_CFG:
            out_path = os.path.join(output_dir, _section_filename(key, fname))
            _plot_section_matplotlib(mesh, scalar, cmap, title, out_path)
            print(f"已保存: {out_path}")
        results[key] = mesh

    print(f"  Matplotlib 出图: {time.perf_counter() - t_render:.1f}s")
    print(f"截面云图总耗时: {time.perf_counter() - t_all:.1f}s")
    return results


if __name__ == "__main__":
    import sys
    if len(sys.argv) != 4:
        print("用法: python -m src.QJZ_fluent_post.symmetry_plot <cas.h5> <dat.h5> <output_dir>")
        sys.exit(1)
    plot_symmetry(sys.argv[1], sys.argv[2], sys.argv[3])
