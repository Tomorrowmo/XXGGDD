"""Wall 边界压力与黏性力面积分。"""

from __future__ import annotations

import h5py
import numpy as np

from .zones import parse_zones, FLUENT_ZONE_TYPE_WALL
from .face_geometry import build_face_geometry


def compute_wall_forces(cas_file: str, dat_file: str, *, verbose: bool = False) -> dict:
    """
    对所有 type==wall 的 zone 积分压力与黏性力。

    返回 dict: zone_name -> {
        n_faces, area,
        F_pressure (3,), F_viscous (3,), F_total (3,)
    }
    """
    zones = parse_zones(cas_file)
    wall_zones = [z for z in zones if z["type"] == FLUENT_ZONE_TYPE_WALL]

    with h5py.File(dat_file, "r") as fd:
        face_pressure_all = fd["results/1/phase-1/faces/SV_P/1"][:]
        wall_shear_all = fd["results/1/phase-1/faces/SV_WALL_SHEAR/1"][:]

    if verbose:
        total_wall_faces = sum(z["n_faces"] for z in wall_zones)
        print(f"Wall 面总数: {total_wall_faces}  (SV_WALL_SHEAR shape[0]: {wall_shear_all.shape[0]})")
        print(f"\n{'='*70}")
        print(
            f"{'Zone名称':<30} {'面数':>8} {'面积/m²':>12} "
            f"{'Fp_x/N':>12} {'Fp_y/N':>12} {'Fp_z/N':>12} "
            f"{'Fv_x/N':>12} {'Fv_y/N':>12} {'Fv_z/N':>12}"
        )
        print(f"{'-'*70}")

    wall_zones_sorted = sorted(wall_zones, key=lambda z: z["min_fid"])
    results: dict = {}
    shear_offset = 0

    for z in wall_zones_sorted:
        f_min = z["min_fid"] - 1
        f_max = z["max_fid"]
        nf = z["n_faces"]

        face_indices = range(f_min, f_max)
        normals, areas, _ = build_face_geometry(cas_file, face_indices)

        p_vals = face_pressure_all[f_min:f_max]
        f_press = np.sum(p_vals[:, None] * (-normals) * areas[:, None], axis=0)

        shear_block = wall_shear_all[shear_offset : shear_offset + nf]
        f_visc = shear_block.sum(axis=0)
        shear_offset += nf

        f_total = f_press + f_visc
        results[z["name"]] = {
            "n_faces": nf,
            "area": float(areas.sum()),
            "F_pressure": f_press,
            "F_viscous": f_visc,
            "F_total": f_total,
        }

        if verbose:
            print(
                f"{z['name']:<30} {nf:>8} {areas.sum():>12.4f} "
                f"{f_press[0]:>12.4f} {f_press[1]:>12.4f} {f_press[2]:>12.4f} "
                f"{f_visc[0]:>12.4f} {f_visc[1]:>12.4f} {f_visc[2]:>12.4f}"
            )

    if verbose:
        all_fp = np.sum([r["F_pressure"] for r in results.values()], axis=0)
        all_fv = np.sum([r["F_viscous"] for r in results.values()], axis=0)
        print(f"\n{'全部Wall合计':<30} {'':>8} {'':>12} "
              f"{all_fp[0]:>12.4f} {all_fp[1]:>12.4f} {all_fp[2]:>12.4f} "
              f"{all_fv[0]:>12.4f} {all_fv[1]:>12.4f} {all_fv[2]:>12.4f}")
        print(
            f"  总合力 Fx={all_fp[0]+all_fv[0]:.4f}  "
            f"Fy={all_fp[1]+all_fv[1]:.4f}  Fz={all_fp[2]+all_fv[2]:.4f}  N"
        )

    return results


def wall_forces_to_serializable(results: dict) -> dict:
    """转为 JSON 友好结构，并给出 x 方向全壁面合计。"""
    from .output_cache import json_safe_float as _sf

    walls = []
    sum_p = np.zeros(3)
    sum_v = np.zeros(3)
    for name, r in results.items():
        fp = r["F_pressure"]
        fv = r["F_viscous"]
        ft = r["F_total"]
        sum_p += fp
        sum_v += fv
        walls.append({
            "name": name,
            "n_faces": int(r["n_faces"]),
            "area": _sf(r["area"]),
            "fx_pressure": _sf(fp[0]),
            "fy_pressure": _sf(fp[1]),
            "fz_pressure": _sf(fp[2]),
            "fx_viscous": _sf(fv[0]),
            "fy_viscous": _sf(fv[1]),
            "fz_viscous": _sf(fv[2]),
            "fx_total": _sf(ft[0]),
            "fy_total": _sf(ft[1]),
            "fz_total": _sf(ft[2]),
        })

    sum_t = sum_p + sum_v
    return {
        "walls": walls,
        "sum_all": {
            "fx_pressure": _sf(sum_p[0]),
            "fx_viscous": _sf(sum_v[0]),
            "fx_total": _sf(sum_t[0]),
        },
    }


def _fmt_plain(x: float, decimals: int = 3) -> str:
    """非科学计数法字符串，去掉多余末尾 0。"""
    if not np.isfinite(x):
        return "nan"
    s = f"{float(x):.{decimals}f}"
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    return s if s else "0"


def save_wall_forces_report_txt(
    output_txt: str,
    payload: dict,
    *,
    cas_file: str,
    dat_file: str,
) -> None:
    """
    将壁面力结果写入 UTF-8 文本：含各壁面三分量力与全壁面合计。
    payload 为 wall_forces_to_serializable 的返回值。
    """
    from pathlib import Path

    path = Path(output_txt)
    path.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    lines.append("# Fluent 壁面力积分结果")
    lines.append(f"# cas: {cas_file}")
    lines.append(f"# dat: {dat_file}")
    lines.append("# 力单位: N, 面积单位: m^2")
    lines.append("")

    lines.append("[全部壁面合计]")
    lines.append(
        "\t".join([
            "Fx_pressure",
            "Fy_pressure",
            "Fz_pressure",
            "Fx_viscous",
            "Fy_viscous",
            "Fz_viscous",
            "Fx_total",
            "Fy_total",
            "Fz_total",
        ])
    )
    # 从 walls 反算全部分量合计（sum_all 仅含 x，此处写全分量更完整）
    walls = payload.get("walls") or []
    sp = np.zeros(3)
    sv = np.zeros(3)
    for w in walls:
        sp += np.array([
            w["fx_pressure"], w["fy_pressure"], w["fz_pressure"],
        ], dtype=float)
        sv += np.array([
            w["fx_viscous"], w["fy_viscous"], w["fz_viscous"],
        ], dtype=float)
    st = sp + sv
    lines.append(
        "\t".join([
            _fmt_plain(sp[0]), _fmt_plain(sp[1]), _fmt_plain(sp[2]),
            _fmt_plain(sv[0]), _fmt_plain(sv[1]), _fmt_plain(sv[2]),
            _fmt_plain(st[0]), _fmt_plain(st[1]), _fmt_plain(st[2]),
        ])
    )
    lines.append("")
    lines.append("[各壁面]")
    lines.append(
        "\t".join([
            "name",
            "n_faces",
            "area_m2",
            "Fx_p", "Fy_p", "Fz_p",
            "Fx_v", "Fy_v", "Fz_v",
            "Fx_t", "Fy_t", "Fz_t",
        ])
    )
    for w in walls:
        lines.append(
            "\t".join([
                str(w.get("name", "")),
                str(int(w.get("n_faces", 0))),
                _fmt_plain(float(w.get("area", 0.0))),
                _fmt_plain(w["fx_pressure"]),
                _fmt_plain(w["fy_pressure"]),
                _fmt_plain(w["fz_pressure"]),
                _fmt_plain(w["fx_viscous"]),
                _fmt_plain(w["fy_viscous"]),
                _fmt_plain(w["fz_viscous"]),
                _fmt_plain(w["fx_total"]),
                _fmt_plain(w["fy_total"]),
                _fmt_plain(w["fz_total"]),
            ])
        )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
