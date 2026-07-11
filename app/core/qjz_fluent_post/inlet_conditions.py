"""入口边界（名称含 inlet）面邻接单元平均量与质量流量。"""

from __future__ import annotations

from pathlib import Path

import h5py
import numpy as np

from .output_cache import json_safe_float as _sf
from .zones import parse_zones


ZONE_TYPE_MAP = {
    3: "wall",
    4: "pressure-inlet",
    5: "pressure-outlet",
    7: "symmetry",
    10: "velocity-inlet",
    20: "mass-flow-inlet",
}


def compute_inlet_report(cas_file: str, dat_file: str) -> list[dict]:
    """
    返回每个入口 zone 的字典列表（JSON 可序列化浮点数）。
    质量流量为对该 zone 所有面的 SV_FLUX 求和再取 Fluent 约定符号（与 test_qjz 一致取负）。
    """
    zones = parse_zones(cas_file)
    inlet_zones = [z for z in zones if "inlet" in z["name"].lower()]
    if not inlet_zones:
        return []

    with h5py.File(dat_file, "r") as fd:
        face_flux = fd["results/1/phase-1/faces/SV_FLUX/1"][:]
        cell_p = fd["results/1/phase-1/cells/SV_P/1"][:]
        cell_t = fd["results/1/phase-1/cells/SV_T/1"][:]
        cell_u = fd["results/1/phase-1/cells/SV_U/1"][:]
        cell_v = fd["results/1/phase-1/cells/SV_V/1"][:]
        cell_w = fd["results/1/phase-1/cells/SV_W/1"][:]

    with h5py.File(cas_file, "r") as fc:
        c0_all = fc["meshes/1/faces/c0/1"][:]

    rows: list[dict] = []
    for z in inlet_zones:
        f_min = z["min_fid"] - 1
        f_max = z["max_fid"]
        nf = z["n_faces"]
        ztype = ZONE_TYPE_MAP.get(z["type"], f"unknown({z['type']})")
        cids = c0_all[f_min:f_max] - 1
        if cids.size == 0:
            continue
        u_mean = _sf(cell_u[cids].mean())
        v_mean = _sf(cell_v[cids].mean())
        w_mean = _sf(cell_w[cids].mean())
        vel_mag = _sf(np.sqrt(cell_u[cids] ** 2 + cell_v[cids] ** 2 + cell_w[cids] ** 2).mean())
        p_mean = _sf(cell_p[cids].mean())
        t_mean = _sf(cell_t[cids].mean())
        mass_flow = _sf(-1.0 * face_flux[f_min:f_max].sum())
        rows.append({
            "name": z["name"],
            "zone_type": ztype,
            "velocity_ms": vel_mag,
            "pressure_pa": p_mean,
            "pressure_mpa": p_mean / 1e6,
            "temperature_k": t_mean,
            "mass_flow_kgs": mass_flow,
            "n_faces": int(nf),
        })
    return rows


def save_inlet_report_txt(output_txt: str, rows: list[dict], *, cas_file: str, dat_file: str) -> None:
    path = Path(output_txt)
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Fluent 入口边界参数（名称含 inlet）",
        f"# cas: {cas_file}",
        f"# dat: {dat_file}",
        "# 速度: m/s, 静压: Pa, 静温: K, 质量流量: kg/s",
        "",
    ]
    if not rows:
        lines.append("(未找到名称中包含 inlet 的边界)")
    else:
        lines.append(
            "\t".join([
                "name", "zone_type", "velocity_m_s", "P_Pa", "P_MPa", "T_K", "mass_flow_kg_s", "n_faces",
            ])
        )
        for r in rows:
            lines.append(
                "\t".join([
                    str(r["name"]),
                    str(r["zone_type"]),
                    f"{r['velocity_ms']:.6f}",
                    f"{r['pressure_pa']:.6f}",
                    f"{r['pressure_mpa']:.6f}",
                    f"{r['temperature_k']:.6f}",
                    f"{r['mass_flow_kgs']:.6f}",
                    str(r["n_faces"]),
                ])
            )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
