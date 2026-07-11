"""沿 x 方向的薄层单元面平均参数与单参数曲线图。"""

from __future__ import annotations

import os
from pathlib import Path

import h5py
import numpy as np
import pandas as pd

# 与 test_qjz 一致：燃烧场近似
GAMMA = 1.3
RS = 287.0

FIELD_SPECS = [
    # {"key": "P_static", "file_tag": "p", "title": "沿程面平均 — 静压", "y_label": "静压", "y_unit": "Pa"},
    # {"key": "T_static", "file_tag": "T", "title": "沿程面平均 — 静温", "y_label": "静温", "y_unit": "K"},
    # {"key": "Mach", "file_tag": "Ma", "title": "沿程面平均 — 马赫数", "y_label": "马赫数", "y_unit": "1"},
    # {"key": "T0", "file_tag": "T0", "title": "沿程面平均 — 总温", "y_label": "总温", "y_unit": "K"},
    # {"key": "P0", "file_tag": "P0", "title": "沿程面平均 — 总压", "y_label": "总压", "y_unit": "Pa"},
    # {"key": "HRR", "file_tag": "HRR", "title": "沿程面平均 — 释热率", "y_label": "释热率", "y_unit": "W/m³"},
    {"key": "P_static", "file_tag": "p", "title": "X-Slice Avg — Static Pressure", "y_label": "Static Pressure", "y_unit": "Pa"},
    {"key": "T_static", "file_tag": "T", "title": "X-Slice Avg — Static Temperature", "y_label": "Static Temperature", "y_unit": "K"},
    {"key": "Mach", "file_tag": "Ma", "title": "X-Slice Avg — Mach Number", "y_label": "Mach Number", "y_unit": "1"},
    {"key": "T0", "file_tag": "T0", "title": "X-Slice Avg — Total Temperature", "y_label": "Total Temperature", "y_unit": "K"},
    {"key": "P0", "file_tag": "P0", "title": "X-Slice Avg — Total Pressure", "y_label": "Total Pressure", "y_unit": "Pa"},
    {"key": "HRR", "file_tag": "HRR", "title": "X-Slice Avg — Heat Release Rate", "y_label": "Heat Release Rate", "y_unit": "W/m³"},
]


def _finite_minmax(arr: np.ndarray, default: tuple[float, float] = (0.0, 1.0)) -> tuple[float, float]:
    a = np.asarray(arr, dtype=float).ravel()
    a = a[np.isfinite(a)]
    if a.size == 0:
        return default
    lo, hi = float(a.min()), float(a.max())
    if lo >= hi:
        hi = lo + 1.0
    return lo, hi


def _parse_axis_limit(v, default: float) -> float:
    if v is None or v == "":
        return default
    try:
        x = float(v)
    except (TypeError, ValueError):
        return default
    return x if np.isfinite(x) else default


def x_slice_plot_filename(field_key: str) -> str:
    """
    按物理量区分的 PNG 文件名，例如 x_slice_plot_p.png、x_slice_plot_T.png。
    未知 key 时退化为 x_slice_plot_<field_key>.png。
    """
    spec = next((s for s in FIELD_SPECS if s["key"] == field_key), None)
    tag = spec["file_tag"] if spec else field_key.replace(" ", "_")
    return f"x_slice_plot_{tag}.png"


def _n_cells_from_dat(dat_file: str) -> int:
    with h5py.File(dat_file, "r") as fd:
        return int(fd["results/1/phase-1/cells/SV_P/1"].shape[0])


def build_volume_mesh(cas_file: str, dat_file: str) -> dict[str, np.ndarray]:
    with h5py.File(dat_file, "r") as fd:
        cell_p = fd["results/1/phase-1/cells/SV_P/1"][:]
        cell_t = fd["results/1/phase-1/cells/SV_T/1"][:]
        cell_u = fd["results/1/phase-1/cells/SV_U/1"][:]
        cell_v = fd["results/1/phase-1/cells/SV_V/1"][:]
        cell_w = fd["results/1/phase-1/cells/SV_W/1"][:]
        cell_rho = fd["results/1/phase-1/cells/SV_DENSITY/1"][:]
        try:
            cell_hrr = fd["results/1/phase-1/cells/SV_TOT_RXN/1"][:]
        except KeyError:
            cell_hrr = np.zeros_like(cell_p)

    vel_mag = np.sqrt(cell_u**2 + cell_v**2 + cell_w**2)
    a_sq = np.maximum(GAMMA * cell_p / cell_rho, 1e-6)
    mach = vel_mag / np.sqrt(a_sq)
    t0 = cell_t * (1 + (GAMMA - 1) / 2 * mach**2)
    p0 = cell_p * (1 + (GAMMA - 1) / 2 * mach**2) ** (GAMMA / (GAMMA - 1))

    return {
        "cell_P": cell_p,
        "cell_T": cell_t,
        "mach": mach,
        "T0": t0,
        "P0": p0,
        "HRR": cell_hrr,
        "vel_mag": vel_mag,
    }


def build_cell_centers(cas_file: str, n_cells: int) -> np.ndarray:
    with h5py.File(cas_file, "r") as f:
        coords = f["meshes/1/nodes/coords/1"][:]
        all_nn = f["meshes/1/faces/nodes/1/nnodes"][:]
        all_fn = f["meshes/1/faces/nodes/1/nodes"][:]
        c0 = f["meshes/1/faces/c0/1"][:]

    cell_sum = np.zeros((n_cells, 3), dtype=np.float64)
    cell_count = np.zeros(n_cells, dtype=np.int32)
    offsets = np.zeros(len(all_nn) + 1, dtype=np.int64)
    np.cumsum(all_nn, out=offsets[1:])
    n_faces = len(all_nn)
    chunk = 500_000
    for start in range(0, n_faces, chunk):
        end = min(start + chunk, n_faces)
        for fi in range(start, end):
            s = int(offsets[fi])
            e = int(offsets[fi + 1])
            fc = coords[all_fn[s:e] - 1].mean(axis=0)
            cid = int(c0[fi]) - 1
            if 0 <= cid < n_cells:
                cell_sum[cid] += fc
                cell_count[cid] += 1
    mask = cell_count > 0
    return np.where(mask[:, None], cell_sum / np.maximum(cell_count[:, None], 1), 0.0)


def run_x_slice_analysis(
    cas_file: str,
    dat_file: str,
    output_dir: str,
    *,
    n_slices: int = 100,
) -> tuple[Path, dict]:
    """
    计算沿 x 薄层平均，写入 x_slice_averaged.csv。
    返回 (csv_path, meta) meta 含默认坐标范围、各场 y 默认 min/max。
    """
    os.makedirs(output_dir, exist_ok=True)
    n_cells = _n_cells_from_dat(dat_file)
    fields = build_volume_mesh(cas_file, dat_file)
    cell_centers = build_cell_centers(cas_file, n_cells)
    cx = cell_centers[:, 0]
    valid_cx = np.isfinite(cx)
    if not np.any(valid_cx):
        raise ValueError("沿程面平均：无有效单元中心 X 坐标，请检查 cas/dat 网格")

    cx_v = cx[valid_cx]
    x_min, x_max = float(cx_v.min()), float(cx_v.max())
    x_span = x_max - x_min
    x_vals = np.linspace(x_min, x_max, n_slices) if n_slices > 1 else np.array([x_min])
    # x 方向所有单元共线时，层厚不能为 0，否则切片匹配不到任何单元
    if x_span < 1e-12:
        half = max(abs(x_min) * 1e-6, 1e-9)
    else:
        half = max(x_span / max(n_slices, 1) * 0.5, 1e-12)

    field_names = ["P_static", "T_static", "Mach", "T0", "P0", "HRR"]
    field_data = [
        fields["cell_P"],
        fields["cell_T"],
        fields["mach"],
        fields["T0"],
        fields["P0"],
        fields["HRR"],
    ]
    records = []
    for xi in x_vals:
        mask = valid_cx & (cx >= xi - half) & (cx <= xi + half)
        n = int(mask.sum())
        if n == 0:
            row = [xi] + [np.nan] * len(field_names)
        else:
            row = [xi] + [float(fd[mask].mean()) for fd in field_data]
        records.append(row)

    df = pd.DataFrame(records, columns=["X_m"] + field_names)
    csv_path = Path(output_dir) / "x_slice_averaged.csv"
    df.to_csv(csv_path, index=False, float_format="%.8g")

    x_mm = df["X_m"].values * 1000.0
    x_def_lo, x_def_hi = _finite_minmax(x_mm, (0.0, 1.0))
    meta = {
        "x_min_mm": x_def_lo,
        "x_max_mm": x_def_hi,
        "fields": [],
    }
    for spec in FIELD_SPECS:
        k = spec["key"]
        col = df[k].astype(float)
        valid = col[np.isfinite(col)]
        if len(valid) == 0:
            ymin, ymax = 0.0, 1.0
        else:
            ymin, ymax = float(valid.min()), float(valid.max())
            if ymin == ymax:
                ymax = ymin + 1e-9
        meta["fields"].append({
            "key": k,
            "label": spec["y_label"],
            "title": spec["title"],
            "y_unit": spec["y_unit"],
            "y_min_default": ymin,
            "y_max_default": ymax,
            "plot_file": x_slice_plot_filename(k),
        })
    return csv_path, meta


def plot_x_slice_field(
    csv_path: str,
    field_key: str,
    output_png: str | None = None,
    *,
    x_min_mm: float | None = None,
    x_max_mm: float | None = None,
    y_min: float | None = None,
    y_max: float | None = None,
) -> str:
    """
    绘制单场沿程曲线。若未指定 output_png，则使用与场量关联的默认文件名（见 x_slice_plot_filename）。
    返回实际写入的 PNG 绝对路径字符串。
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    # matplotlib.rcParams['font.family'] = 'Noto Serif CJK SC'  # 中文标签已移除，无需中文字体
    matplotlib.rcParams['axes.unicode_minus'] = False

    if output_png is None:
        output_png = str(Path(csv_path).parent / x_slice_plot_filename(field_key))
    out_p = Path(output_png)

    df = pd.read_csv(csv_path)
    if field_key not in df.columns:
        raise ValueError(f"未知场量: {field_key}")
    x_mm = df["X_m"].values * 1000.0
    y = df[field_key].values.astype(float)

    spec = next((s for s in FIELD_SPECS if s["key"] == field_key), None)
    if spec is None:
        raise ValueError(field_key)

    x_def_lo, x_def_hi = _finite_minmax(x_mm, (0.0, 1.0))
    y_def_lo, y_def_hi = _finite_minmax(y, (0.0, 1.0))
    x_min_mm = _parse_axis_limit(x_min_mm, x_def_lo)
    x_max_mm = _parse_axis_limit(x_max_mm, x_def_hi)
    y_min = _parse_axis_limit(y_min, y_def_lo)
    y_max = _parse_axis_limit(y_max, y_def_hi)
    if x_min_mm >= x_max_mm:
        x_max_mm = x_min_mm + 1.0
    if y_min >= y_max:
        y_max = y_min + 1.0

    fig, ax = plt.subplots(figsize=(8, 4.5))
    finite = np.isfinite(x_mm) & np.isfinite(y)
    if np.any(finite):
        ax.plot(x_mm[finite], y[finite], color="#5e81ac", linewidth=1.5)
    else:
        ax.text(0.5, 0.5, "No valid data", ha="center", va="center", transform=ax.transAxes)
    ax.set_xlim(x_min_mm, x_max_mm)
    ax.set_ylim(y_min, y_max)
    ax.set_xlabel("X Position / mm")
    ytitle = f"{spec['y_label']} / {spec['y_unit']}" if spec["y_unit"] != "1" else spec["y_label"]
    ax.set_ylabel(ytitle)
    ax.set_title(spec["title"])
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    out_p.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(str(out_p), dpi=150, bbox_inches="tight")
    plt.close(fig)
    return str(out_p.resolve())
