"""从算例 Output/ 目录读取或清理已保存的后处理结果。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

import numpy as np
import pandas as pd

from .symmetry_plot import FIELD_CFG, section_image_meta
from .x_slice_average import FIELD_SPECS, x_slice_plot_filename, _finite_minmax

INLET_TXT = "inlet_parameters.txt"
WALL_TXT = "wall_forces.txt"
XSLICE_CSV = "x_slice_averaged.csv"
XSLICE_META = "x_slice_meta.json"


def resolve_case_output_dir(
    cas_p: Path,
    case_dir: Path,
    fallback: Path,
    case_name: str | None = None,
) -> Path:
    """定位算例 Output/；优先 case_name，其次 cas 相对 Case 的路径。"""
    cas_p = cas_p.resolve()
    case_dir = case_dir.resolve()
    candidates: list[Path] = []

    if case_name:
        safe = case_name.strip()
        if safe and safe not in (".", "..") and "/" not in safe and "\\" not in safe:
            candidates.append((case_dir / safe / "Output").resolve())

    try:
        rel = cas_p.relative_to(case_dir)
        if rel.parts:
            candidates.append((case_dir / rel.parts[0] / "Output").resolve())
    except ValueError:
        pass

    seen: set[str] = set()
    unique: list[Path] = []
    for c in candidates:
        key = str(c)
        if key not in seen:
            seen.add(key)
            unique.append(c)

    for c in unique:
        if c.is_dir() and any((c / fn).is_file() for fn in (WALL_TXT, INLET_TXT, XSLICE_CSV)):
            return c

    if unique:
        out = unique[0]
        out.mkdir(parents=True, exist_ok=True)
        return out

    fallback.mkdir(parents=True, exist_ok=True)
    return fallback.resolve()


def parse_force_flag(value) -> bool:
    """解析 JSON 中的 force 字段（避免字符串 \"false\" 被 bool() 当成 True）。"""
    if value is None:
        return False
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "on")
    return bool(value)

# 可清理的输出文件/模式（保留目录本身）
_OUTPUT_GLOBS = [
    INLET_TXT,
    WALL_TXT,
    XSLICE_CSV,
    XSLICE_META,
    "symmetry_*.png",
    "section_*.png",
    "x_slice_plot_*.png",
]


def _parse_float(s: str) -> float:
    try:
        v = float(s.strip())
    except (TypeError, ValueError):
        return 0.0
    return v if np.isfinite(v) else 0.0


def json_safe_float(x, default: float = 0.0) -> float:
    """JSON 可序列化的有限浮点数。"""
    try:
        v = float(x)
    except (TypeError, ValueError):
        return default
    return v if np.isfinite(v) else default


def json_sanitize(obj):
    """递归去除 NaN/Inf，避免 JSONResponse 报错。"""
    if isinstance(obj, dict):
        return {k: json_sanitize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [json_sanitize(v) for v in obj]
    if isinstance(obj, tuple):
        return [json_sanitize(v) for v in obj]
    if isinstance(obj, (np.floating, float)):
        v = float(obj)
        return v if np.isfinite(v) else None
    if isinstance(obj, (np.integer, int)) and not isinstance(obj, bool):
        return int(obj)
    if isinstance(obj, np.ndarray):
        return json_sanitize(obj.tolist())
    return obj


def parse_inlet_report_txt(path: Path) -> list[dict] | None:
    """解析 inlet_parameters.txt，失败或不存在返回 None。"""
    if not path.is_file():
        return None
    rows: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("name\t") or line.startswith("(未找到"):
            continue
        parts = line.split("\t")
        if len(parts) < 8:
            continue
        rows.append({
            "name": parts[0],
            "zone_type": parts[1],
            "velocity_ms": _parse_float(parts[2]),
            "pressure_pa": _parse_float(parts[3]),
            "pressure_mpa": _parse_float(parts[4]),
            "temperature_k": _parse_float(parts[5]),
            "mass_flow_kgs": _parse_float(parts[6]),
            "n_faces": int(float(parts[7])),
        })
    return rows if rows else None


def _split_tsv(line: str) -> list[str]:
    if "\t" in line:
        return line.split("\t")
    return line.split()


def parse_wall_forces_txt(path: Path) -> dict | None:
    """解析 wall_forces.txt，返回与 wall_forces_to_serializable 相同结构。"""
    if not path.is_file():
        return None
    walls: list[dict] = []
    section = ""
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("[") and "壁面" in line:
            section = "walls"
            continue
        if line.startswith("[") and "合计" in line:
            section = "sum"
            continue
        if line.startswith("Fx_pressure") or line.startswith("name"):
            continue
        parts = _split_tsv(line)
        if len(parts) >= 12 and (section == "walls" or parts[0] not in ("name", "Fx_pressure")):
            try:
                walls.append({
                    "name": parts[0],
                    "n_faces": int(float(parts[1])),
                    "area": _parse_float(parts[2]),
                    "fx_pressure": _parse_float(parts[3]),
                    "fy_pressure": _parse_float(parts[4]),
                    "fz_pressure": _parse_float(parts[5]),
                    "fx_viscous": _parse_float(parts[6]),
                    "fy_viscous": _parse_float(parts[7]),
                    "fz_viscous": _parse_float(parts[8]),
                    "fx_total": _parse_float(parts[9]),
                    "fy_total": _parse_float(parts[10]),
                    "fz_total": _parse_float(parts[11]),
                })
            except (TypeError, ValueError):
                continue
    if not walls:
        return None
    sum_p = np.zeros(3)
    sum_v = np.zeros(3)
    for w in walls:
        sum_p += [w["fx_pressure"], w["fy_pressure"], w["fz_pressure"]]
        sum_v += [w["fx_viscous"], w["fy_viscous"], w["fz_viscous"]]
    sum_t = sum_p + sum_v
    return {
        "walls": walls,
        "sum_all": {
            "fx_pressure": float(sum_p[0]),
            "fx_viscous": float(sum_v[0]),
            "fx_total": float(sum_t[0]),
        },
    }


def section_pngs_complete(out_dir: Path, section_key: str) -> bool:
    """某截面 3 张云图是否均已存在。"""
    meta = next((s for s in section_image_meta() if s["key"] == section_key), None)
    if meta is None:
        return False
    return all((out_dir / im["filename"]).is_file() for im in meta["images"])


def build_x_slice_meta_from_csv(csv_path: Path) -> dict:
    """由 CSV 重建沿程 meta（与 run_x_slice_analysis 输出结构一致）。"""
    df = pd.read_csv(csv_path)
    x_mm = df["X_m"].values.astype(float) * 1000.0
    x_def_lo, x_def_hi = _finite_minmax(x_mm, (0.0, 1.0))
    meta = {
        "x_min_mm": x_def_lo,
        "x_max_mm": x_def_hi,
        "fields": [],
    }
    for spec in FIELD_SPECS:
        k = spec["key"]
        if k not in df.columns:
            continue
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
    return meta


def load_symmetry_sections(
    out_dir: Path,
    url_builder: Callable[[list[str]], list[str]],
    *,
    section_keys: list[str] | None = None,
) -> list[dict]:
    """读取已存在的截面云图元数据（含 URL）。"""
    sections: list[dict] = []
    for sec in section_image_meta():
        if section_keys is not None and sec["key"] not in section_keys:
            continue
        if not section_pngs_complete(out_dir, sec["key"]):
            continue
        filenames = [m["filename"] for m in sec["images"]]
        urls = url_builder(filenames)
        images = [{**m, "url": u} for m, u in zip(sec["images"], urls)]
        sections.append({"key": sec["key"], "label": sec["label"], "images": images})
    return sections


def output_availability(out_dir: Path) -> dict:
    """返回各结果是否已在 Output 中就绪。"""
    sections = {
        sec["key"]: section_pngs_complete(out_dir, sec["key"])
        for sec in section_image_meta()
    }
    return {
        "inlet": (out_dir / INLET_TXT).is_file(),
        "wall": (out_dir / WALL_TXT).is_file(),
        "sections": sections,
        "xslice": (out_dir / XSLICE_CSV).is_file(),
    }


def load_cached_output(
    out_dir: Path,
    url_builder: Callable[[list[str]], list[str]],
    plot_url_builder: Callable[[str], str],
) -> dict:
    """尽可能从 Output 加载全部已有结果。"""
    out: dict = {
        "from_cache": True,
        "available": output_availability(out_dir),
        "inlets": None,
        "walls": None,
        "sections": [],
        "symmetry_images": [],
        "xslice": None,
        "output_dir": str(out_dir),
    }

    inlets = parse_inlet_report_txt(out_dir / INLET_TXT)
    if inlets is not None:
        out["inlets"] = inlets

    walls = parse_wall_forces_txt(out_dir / WALL_TXT)
    if walls is not None:
        out["walls"] = walls

    sections = load_symmetry_sections(out_dir, url_builder)
    out["sections"] = sections
    sym = next((s for s in sections if s["key"] == "symmetry"), None)
    if sym:
        out["symmetry_images"] = sym["images"]

    csv_path = out_dir / XSLICE_CSV
    if csv_path.is_file():
        meta_path = out_dir / XSLICE_META
        if meta_path.is_file():
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        else:
            meta = build_x_slice_meta_from_csv(csv_path)
        first_key = meta["fields"][0]["key"] if meta.get("fields") else "P_static"
        png_name = x_slice_plot_filename(first_key)
        if not (out_dir / png_name).is_file():
            from .x_slice_average import plot_x_slice_field
            plot_x_slice_field(str(csv_path), first_key, str(out_dir / png_name))
        out["xslice"] = {
            "meta": meta,
            "plot_url": plot_url_builder(png_name),
            "plot_filename": png_name,
            "csv_path": str(csv_path),
        }

    return out


def clear_output_dir(out_dir: Path) -> list[str]:
    """删除 Output 内后处理结果文件，返回已删路径（相对 out_dir）。"""
    deleted: list[str] = []
    if not out_dir.is_dir():
        return deleted
    for pattern in _OUTPUT_GLOBS:
        for p in out_dir.glob(pattern):
            if p.is_file():
                p.unlink()
                deleted.append(p.name)
    return sorted(deleted)
