"""单对象分析 API（v2）—— 仿真/试验详情的真实数据（供仿真分析/试验分析屏）。

数据来自算例的真实文件：试验走可配置解析，仿真走 simparse。种子数据无文件→available=False。
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.db.models import (
    Case, CaseKind, CaseOperatingLink, OperatingPoint, Measurement, Quantity,
)
from app.services import experiment as exp_svc
from app.services import criteria as crit_svc
from app.services import simparse_adapter, viz, sim_analysis

router = APIRouter(prefix="/api/v2/cases", tags=["analysis"])


def _downsample(x: np.ndarray, y: np.ndarray, n: int = 400):
    if len(x) <= n:
        return x, y
    idx = np.linspace(0, len(x) - 1, n).astype(int)
    return x[idx], y[idx]


# 试验解析缓存（按 路径+mtime）：40k 行解析 ~1s，分页/切换物理量时避免每次重解析
_EXP_CACHE: dict = {}


def _parsed_experiment(path: str | Path):
    p = Path(path)
    key = str(p.resolve())
    mt = p.stat().st_mtime
    hit = _EXP_CACHE.get(key)
    if hit and hit[0] == mt:
        return hit[1]
    pe = exp_svc.read_experiment(path)
    _EXP_CACHE[key] = (mt, pe)
    if len(_EXP_CACHE) > 8:                       # 简单限容
        _EXP_CACHE.pop(next(iter(_EXP_CACHE)))
    return pe


def _op_key(db: Session, case: Case) -> str | None:
    link = db.execute(
        select(CaseOperatingLink).where(CaseOperatingLink.case_id == case.id)
    ).scalar_one_or_none()
    if link and link.op_id:
        op = db.get(OperatingPoint, link.op_id)
        if op and op.canonical_key != "__UNALIGNED__":
            return op.canonical_key
    return None


def _case_measurements(db: Session, case: Case) -> dict[str, dict]:
    """算例的库内测量，按 Quantity.key 索引（多源对比的统一数据源）。"""
    out: dict[str, dict] = {}
    for m in db.execute(
        select(Measurement).where(Measurement.case_id == case.id)
    ).scalars().all():
        q = db.get(Quantity, m.quantity_id)
        if q is None:
            continue
        out[q.key] = {"quantity": q.physical_name, "value": m.value,
                      "unit": m.unit, "confidence": m.confidence.value}
    return out


def _parse_ids(ids: str) -> list[int]:
    out = []
    for tok in (ids or "").split(","):
        tok = tok.strip()
        if tok.isdigit():
            out.append(int(tok))
    return out


def _quantity_key_order(db: Session, cases: list[Case],
                        per_case: dict[int, dict[str, dict]]) -> list[str]:
    keys: list[str] = []
    for c in cases:
        for k in per_case[c.id]:
            if k not in keys:
                keys.append(k)
    return keys


@router.get("/{case_id}/experiment")
def experiment_detail(case_id: int, db: Session = Depends(get_db)):
    """试验车次真实分析：通道/统计/阶段/稳态关键量/异常/曲线。"""
    c = db.get(Case, case_id)
    if c is None:
        raise HTTPException(404, "算例不存在")
    if c.kind != CaseKind.EXPERIMENT:
        raise HTTPException(400, "非试验车次")
    path = Path(c.storage_uri)
    if not path.exists():
        return {"available": False, "reason": "原始文件不可用（种子/演示数据无文件，请入库真实 TXT）"}
    try:
        parsed = _parsed_experiment(path)
    except Exception as e:  # noqa: BLE001
        return {"available": False, "reason": f"解析失败：{e}"}
    stats = exp_svc.compute_stats(parsed)
    phases = exp_svc.segment_phases(parsed)
    steady = exp_svc.extract_steady_qoi(parsed, phases)
    anomalies = [a.__dict__ for a in crit_svc.check_experiment_anomalies(stats)]
    corr = exp_svc.settings.experiment.atmos_correction_mpa
    _press = ("流道压力", "室压", "隔离段")
    # 共享 x 的**全通道**下采样序列，供前端自由切换要显示的物理量（无需重新请求）
    xs_ds, _ = _downsample(parsed.time, parsed.time)
    curve_x = [round(float(v), 4) for v in xs_ds]
    series = []
    for ch in parsed.channels:
        col = parsed.data[:, ch["index"]]
        if ch["category"] in _press:
            col = col + corr
        _, ys = _downsample(parsed.time, col)
        series.append({"label": ch["label"], "category": ch["category"],
                       "y": [round(float(v), 4) for v in ys]})
    # curves：默认前 6 路（向后兼容旧前端）
    curves = [{"label": s["label"], "x": curve_x, "y": s["y"]} for s in series[:6]]
    return {"available": True, "n_rows": parsed.n_rows, "n_channels": len(parsed.channels),
            "channels": [c2["label"] for c2 in parsed.channels], "stats": stats,
            "phases": phases.__dict__, "steady_qoi": steady, "anomalies": anomalies,
            "curves": curves, "curve_x": curve_x, "series": series}


@router.get("/{case_id}/experiment/raw")
def experiment_raw(case_id: int, offset: int = 0, limit: int = 50,
                   db: Session = Depends(get_db)):
    """原始数据分页（Time + 各通道原值，未加大气修正）——供"查看原始数据"表格。"""
    c = db.get(Case, case_id)
    if c is None:
        raise HTTPException(404, "算例不存在")
    if c.kind != CaseKind.EXPERIMENT:
        raise HTTPException(400, "非试验车次")
    path = Path(c.storage_uri)
    if not path.exists():
        return {"available": False, "reason": "原始文件不可用"}
    try:
        parsed = _parsed_experiment(path)
    except Exception as e:  # noqa: BLE001
        return {"available": False, "reason": f"解析失败：{e}"}
    limit = max(1, min(int(limit), 500))
    offset = max(0, int(offset))
    tcol = exp_svc.settings.experiment.time_column
    cols = [tcol] + [ch["index"] for ch in parsed.channels]
    headers = ["Time (s)"] + [ch["label"] for ch in parsed.channels]
    rows = []
    for r in range(offset, min(offset + limit, parsed.n_rows)):
        rows.append([round(float(parsed.data[r, ci]), 5) for ci in cols])
    return {"available": True, "total": parsed.n_rows, "offset": offset, "limit": limit,
            "headers": headers, "rows": rows}


def _sim_overview(s: dict) -> dict:
    """从 simparse 概况提取专业概览字段（去 _provenance 噪声）。"""
    def g(*ks):
        for k in ks:
            if k in s and s[k] is not None:
                return s[k]
        return None
    turb = s.get("turbulence") or {}
    thermo = s.get("thermophysics") or {}
    comb = s.get("combustion") or {}
    chem = s.get("chemistry") or {}
    tt = thermo.get("thermoType") if isinstance(thermo, dict) else None
    return {
        "solver": g("solver", "application"), "format": g("format"), "version": g("version"),
        "layout": g("layout"), "transient": s.get("is_transient"), "completed": s.get("is_completed"),
        "turbulence": (turb.get("RASModel") or turb.get("LESModel") or turb.get("simulationType"))
        if isinstance(turb, dict) else turb,
        "sim_type": turb.get("simulationType") if isinstance(turb, dict) else None,
        "transport": (tt.get("transport") if isinstance(tt, dict) else None),
        "thermo_type": (tt.get("type") if isinstance(tt, dict) else None),
        "combustion": comb.get("combustionModel") if isinstance(comb, dict) else comb,
        "chemistry": (chem.get("chemistryType", {}) or {}).get("method") if isinstance(chem, dict) else None,
        "decomposition": (s.get("decomposition") or {}).get("numberOfSubdomains") if isinstance(s.get("decomposition"), dict) else None,
        "gravity": s.get("gravity"),
    }


def _sim_mesh(s: dict) -> dict:
    bnds = s.get("boundaries") or []
    zones = s.get("mesh_zones") or []
    return {
        "cells": s.get("mesh_cells"), "points": s.get("mesh_points"),
        "faces": s.get("mesh_faces"), "internal_faces": s.get("mesh_internal_faces"),
        "n_boundaries": len(bnds) if isinstance(bnds, list) else None,
        "boundaries": [{"name": b.get("name"), "type": b.get("type"), "n_faces": b.get("nFaces")}
                       for b in bnds if isinstance(b, dict)][:20] if isinstance(bnds, list) else [],
        "zones": [{"name": z.get("name"), "role": z.get("role"), "n_cells": z.get("n_cells")}
                  for z in zones if isinstance(z, dict)] if isinstance(zones, list) else [],
    }


def _sim_variables(fields: dict) -> list[dict]:
    vr = (fields or {}).get("variable_ranges") or {}
    out = []
    for name, rng in vr.items():
        if not isinstance(rng, dict):
            continue
        mn, mx = rng.get("min"), rng.get("max")
        if mn is None and mx is None:
            continue
        # 跳过全零场（大量未参与组分），保留有量程的
        if (mn == 0 and mx == 0):
            continue
        out.append({"name": name, "min": mn, "max": mx, "mean": rng.get("mean")})
    return out


def _sim_residuals(fields: dict) -> dict:
    rh = (fields or {}).get("residual_history") or {}
    co = (fields or {}).get("convergence_orders") or {}
    cs = (fields or {}).get("convergence_summary") or {}
    def _scalar(v):
        # residual_history 元素可能是标量，也可能是 [iter, residual] 对
        if isinstance(v, (list, tuple)):
            v = v[-1] if v else None
        try:
            return None if v is None else round(float(v), 8)
        except (TypeError, ValueError):
            return None
    series = {}
    for var, vals in rh.items():
        if isinstance(vals, list) and vals:
            series[var] = [_scalar(v) for v in vals[-200:]]
    return {"series": series, "orders": co, "summary": cs}


def _sim_expert(overview: dict, conv: list, qoi_items: list, mesh: dict) -> dict:
    """确定性五段式专家小结（部署机可再由 agent「渊」增强）。"""
    def find(items, name):
        for x in items:
            if isinstance(x, dict) and x.get("variable") == name:
                return x.get("value")
        return None
    converged = find(conv, "is_steady_state_converged")
    diverged = find(conv, "is_diverged")
    orders_max = find(conv, "convergence_orders_max")
    tmax = find(qoi_items, "T_max")
    n_qoi = len([x for x in qoi_items if isinstance(x, dict) and x.get("value") is not None])
    conv_txt = ("已收敛" if converged else "未达稳态收敛") + (f"（残差最大降 {round(float(orders_max),1)} 阶）" if isinstance(orders_max, (int, float)) else "")
    verdict = "数据可信" if (converged and not diverged) else ("发散/未收敛，需复核" if diverged or converged is False else "待复核")
    vc = "good" if verdict == "数据可信" else "warn"
    return {"sections": {
        "概况": f"{overview.get('solver') or '—'} · {overview.get('turbulence') or '—'}"
                + (f" · {overview.get('combustion')} 燃烧" if overview.get('combustion') else ""),
        "网格": f"{mesh.get('cells') or '—'} 单元 · {mesh.get('n_boundaries') or '—'} 边界",
        "收敛": conv_txt,
        "QOI": f"提取 {n_qoi} 项关注量" + (f"，最高温 {round(float(tmax))} K" if isinstance(tmax, (int, float)) else ""),
        "结论": verdict,
    }, "verdict": verdict, "verdict_class": vc}


@router.get("/{case_id}/simulation")
def simulation_detail(case_id: int, db: Session = Depends(get_db)):
    """仿真算例真实分析：概况/网格/变量/收敛(残差·判据)/QOI/切片/专家（专业面板）。"""
    c = db.get(Case, case_id)
    if c is None:
        raise HTTPException(404, "算例不存在")
    if c.kind != CaseKind.SIMULATION:
        raise HTTPException(400, "非仿真算例")
    uri = c.storage_uri
    if not Path(uri).exists():
        return {"available": False, "reason": "原始文件不可用（种子/演示数据无文件，请入库真实算例）"}
    summ = simparse_adapter.summary(uri)
    if not summ.get("available"):
        return {"available": False, "reason": summ.get("reason", "simparse 不可用或无文件")}
    s = summ.get("summary", {})
    conv = simparse_adapter.convergence(uri).get("convergence", [])
    qoi_items = simparse_adapter.qoi(uri).get("qoi", [])
    fields = simparse_adapter.field_stats(uri).get("field_stats", {})
    # 切片**不阻塞**面板加载：只取已缓存图，同时后台起渲染（首次约 1 分钟，前端轮询 /previews）。
    previews = viz.start_previews(uri)
    urls = previews.get("urls", {})
    overview = _sim_overview(s)
    mesh = _sim_mesh(s)
    bc = s.get("bc") if isinstance(s.get("bc"), dict) else None
    return {"available": True,
            "overview": overview, "mesh": mesh, "bc": bc,
            "variables": _sim_variables(fields),
            "residuals": _sim_residuals(fields),
            "convergence": conv, "qoi": qoi_items,
            "expert": _sim_expert(overview, conv, qoi_items, mesh),
            "preview_urls": urls,
            "previews_rendering": bool(previews.get("rendering")),
            "x_slice_available": sim_analysis._is_openfoam(uri)}


@router.get("/{case_id}/vtp")
def vtp_export(case_id: int, db: Session = Depends(get_db)):
    """导出边界面 VTP（供前端 vtk.js 真三维交互：旋转/缩放/按标量上色）。"""
    c = db.get(Case, case_id)
    if c is None:
        raise HTTPException(404, "算例不存在")
    if c.kind != CaseKind.SIMULATION:
        raise HTTPException(400, "非仿真算例")
    if not Path(c.storage_uri).exists():
        return {"available": False, "reason": "原始文件不可用（种子/演示数据无文件）"}
    return viz.start_vtp(c.storage_uri)   # 非阻塞：后台渲染 + 前端轮询，不卡 3D 面板


@router.get("/{case_id}/turntable")
def turntable(case_id: int, n: int = 24, db: Session = Depends(get_db)):
    """绕轴多帧转台图（供三维交互 · 拖拽旋转）。首次生成后缓存。"""
    c = db.get(Case, case_id)
    if c is None:
        raise HTTPException(404, "算例不存在")
    if c.kind != CaseKind.SIMULATION:
        raise HTTPException(400, "非仿真算例")
    if not Path(c.storage_uri).exists():
        return {"available": False, "reason": "原始文件不可用（种子/演示数据无文件）"}
    return viz.generate_turntable(c.storage_uri, n_frames=n)


@router.get("/{case_id}/x-slice")
def x_slice(case_id: int, n_slices: int = 100, db: Session = Depends(get_db)):
    """沿程面平均（静压/静温/马赫/总温/总压）—— 用公式库算真实场（OpenFOAM）。"""
    c = db.get(Case, case_id)
    if c is None:
        raise HTTPException(404, "算例不存在")
    if c.kind != CaseKind.SIMULATION:
        raise HTTPException(400, "非仿真算例")
    return sim_analysis.x_slice_openfoam(c.storage_uri, n_slices=n_slices)


# ------------------------------------------------------------------ 多算例 / 多车次对比
@router.get("/sim-compare")
def sim_compare(ids: str, db: Session = Depends(get_db)):
    """多仿真算例技术性自比（网格无关性 / 参数敏感性）。

    以库内测量为统一数据源，取网格最细者为基准，逐 QOI 算相对基准的偏差。
    不含实验真值、不评级——正式跨单位评判在对比评估。
    """
    id_list = _parse_ids(ids)
    cases = [db.get(Case, i) for i in id_list]
    cases = [c for c in cases if c is not None and c.kind == CaseKind.SIMULATION]
    if len(cases) < 2:
        return {"available": False, "reason": "请至少选择 2 个仿真算例进行对比"}

    per_case = {c.id: _case_measurements(db, c) for c in cases}
    metas = []
    for c in cases:
        ctx = c.context or {}
        metas.append({"id": c.id, "name": c.name, "unit": c.delivery.unit.name,
                      "operating_point": _op_key(db, c),
                      "mesh_cells": ctx.get("mesh_cells"), "y_plus": ctx.get("y_plus"),
                      "solver": ctx.get("solver"), "n_measurements": len(per_case[c.id])})

    # 基准 = 网格最细（mesh_cells 最大）；无网格信息则取最后一个
    def _cells(c: Case) -> float:
        return float((c.context or {}).get("mesh_cells") or 0)
    ref = max(cases, key=_cells)
    ref_id = ref.id if _cells(ref) > 0 else cases[-1].id
    ref_meas = per_case[ref_id]

    keys = _quantity_key_order(db, cases, per_case)
    rows = []
    max_dev = 0.0
    for k in keys:
        sample = next(per_case[c.id][k] for c in cases if k in per_case[c.id])
        refm = ref_meas.get(k)
        values = []
        for c in cases:
            m = per_case[c.id].get(k)
            if m is None:
                values.append({"case_id": c.id, "value": None, "deviation_pct": None,
                               "is_ref": c.id == ref_id})
                continue
            dev = None
            if refm and refm["value"]:
                dev = round((m["value"] - refm["value"]) / abs(refm["value"]) * 100.0, 2)
                if c.id != ref_id:
                    max_dev = max(max_dev, abs(dev))
            values.append({"case_id": c.id, "value": round(m["value"], 6),
                           "deviation_pct": dev, "is_ref": c.id == ref_id})
        rows.append({"quantity": sample["quantity"], "unit": sample["unit"], "values": values})

    if not rows:
        return {"available": False, "reason": "所选算例暂无落库的 QOI，无法对比（请先在单算例分析中提取并入库）"}
    # 网格无关性判定：相对最细网格的最大偏差
    if max_dev <= 1.0:
        verdict, level = f"关键量相对最细网格最大偏差 {max_dev:.1f}%，已达网格无关。", "HIGH"
    elif max_dev <= 3.0:
        verdict, level = f"关键量相对最细网格最大偏差 {max_dev:.1f}%，基本收敛，可用于评估。", "MED"
    else:
        verdict, level = f"关键量相对最细网格最大偏差 {max_dev:.1f}%，偏差偏大，建议加密网格后复核。", "LOW"
    return {"available": True, "cases": metas, "reference_id": ref_id,
            "rows": rows, "max_deviation": round(max_dev, 2),
            "verdict": verdict, "verdict_level": level}


@router.get("/exp-compare")
def exp_compare(ids: str, db: Session = Depends(get_db)):
    """多试验车次重复性核查：同工况下逐关键量算 均值±σ / 变异系数 CV / 离群车次。"""
    id_list = _parse_ids(ids)
    cases = [db.get(Case, i) for i in id_list]
    cases = [c for c in cases if c is not None and c.kind == CaseKind.EXPERIMENT]
    if len(cases) < 2:
        return {"available": False, "reason": "请至少选择 2 个试验车次进行重复性核查"}

    per_case = {c.id: _case_measurements(db, c) for c in cases}
    metas = [{"id": c.id, "name": c.name, "unit": c.delivery.unit.name,
              "operating_point": _op_key(db, c), "n_measurements": len(per_case[c.id])}
             for c in cases]

    keys = _quantity_key_order(db, cases, per_case)
    rows = []
    cv_list = []
    outlier_votes: dict[int, int] = {c.id: 0 for c in cases}
    for k in keys:
        present = [(c, per_case[c.id][k]) for c in cases if k in per_case[c.id]]
        if len(present) < 2:
            continue  # 少于 2 个车次有该量，无法谈重复性
        sample = present[0][1]
        vals = np.array([m["value"] for _, m in present], dtype=float)
        mean = float(vals.mean())
        std = float(vals.std())  # 总体标准差
        cv = (std / abs(mean) * 100.0) if mean else 0.0
        cv_list.append(cv)
        # 离群：CV 偏大时，离均值最远的车次记一票
        far_case_id = None
        if cv > 2.0 and std > 0:
            fi = int(np.argmax(np.abs(vals - mean)))
            far_case_id = present[fi][0].id
            outlier_votes[far_case_id] += 1
        verdict = "一致" if cv <= 2.0 else "关注"
        rows.append({
            "quantity": sample["quantity"], "unit": sample["unit"],
            "values": [{"case_id": c.id, "value": round(m["value"], 6)} for c, m in present],
            "mean": round(mean, 4), "std": round(std, 4), "cv_pct": round(cv, 2),
            "verdict": verdict, "far_case_id": far_case_id,
        })

    if not rows:
        return {"available": False, "reason": "所选车次无共同的落库关键量，无法核查重复性"}
    avg_cv = round(sum(cv_list) / len(cv_list), 2) if cv_list else 0.0
    # 离群车次 = 得票最多且 >=2 票（在多个量上系统性偏离）
    top = max(outlier_votes.items(), key=lambda kv: kv[1])
    outlier_id = top[0] if top[1] >= 2 else None
    # 剔除离群后的平均 CV
    avg_cv_clean = avg_cv
    if outlier_id is not None:
        clean = []
        for row in rows:
            kept = [v for v in row["values"] if v["case_id"] != outlier_id]
            if len(kept) < 2:
                continue
            arr = np.array([v["value"] for v in kept], dtype=float)
            m = float(arr.mean())
            clean.append((float(arr.std()) / abs(m) * 100.0) if m else 0.0)
        if clean:
            avg_cv_clean = round(sum(clean) / len(clean), 2)
    return {"available": True, "cases": metas, "rows": rows,
            "avg_cv": avg_cv, "outlier_case_id": outlier_id,
            "avg_cv_clean": avg_cv_clean, "n_outlier": 1 if outlier_id else 0}
