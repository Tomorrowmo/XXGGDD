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
from app.services import simparse_adapter, viz

router = APIRouter(prefix="/api/v2/cases", tags=["analysis"])


def _downsample(x: np.ndarray, y: np.ndarray, n: int = 400):
    if len(x) <= n:
        return x, y
    idx = np.linspace(0, len(x) - 1, n).astype(int)
    return x[idx], y[idx]


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
        parsed = exp_svc.read_experiment(path)
    except Exception as e:  # noqa: BLE001
        return {"available": False, "reason": f"解析失败：{e}"}
    stats = exp_svc.compute_stats(parsed)
    phases = exp_svc.segment_phases(parsed)
    steady = exp_svc.extract_steady_qoi(parsed, phases)
    anomalies = [a.__dict__ for a in crit_svc.check_experiment_anomalies(stats)]
    corr = exp_svc.settings.experiment.atmos_correction_mpa
    curves = []
    for ch in parsed.channels[:6]:
        col = parsed.data[:, ch["index"]]
        if ch["category"] in ("流道压力", "室压", "隔离段"):
            col = col + corr
        xs, ys = _downsample(parsed.time, col)
        curves.append({"label": ch["label"],
                       "x": [round(float(v), 4) for v in xs],
                       "y": [round(float(v), 4) for v in ys]})
    return {"available": True, "n_rows": parsed.n_rows, "n_channels": len(parsed.channels),
            "channels": [c2["label"] for c2 in parsed.channels], "stats": stats,
            "phases": phases.__dict__, "steady_qoi": steady, "anomalies": anomalies,
            "curves": curves}


@router.get("/{case_id}/simulation")
def simulation_detail(case_id: int, db: Session = Depends(get_db)):
    """仿真算例真实分析：概况/收敛/网格/QOI/切片。"""
    c = db.get(Case, case_id)
    if c is None:
        raise HTTPException(404, "算例不存在")
    if c.kind != CaseKind.SIMULATION:
        raise HTTPException(400, "非仿真算例")
    uri = c.storage_uri
    summ = simparse_adapter.summary(uri)
    if not summ.get("available"):
        return {"available": False, "reason": summ.get("reason", "simparse 不可用或无文件")}
    conv = simparse_adapter.convergence(uri)
    qoi = simparse_adapter.qoi(uri)
    fields = simparse_adapter.field_stats(uri)
    previews = viz.generate_previews(uri)
    urls = {}
    if previews.get("available"):
        key = Path(previews["dir"]).name
        urls = {n: f"/previews/{key}/{fn}" for n, fn in previews.get("images", {}).items()}
    return {"available": True, "summary": summ.get("summary", {}),
            "convergence": conv.get("convergence", []), "qoi": qoi.get("qoi", []),
            "field_stats": fields.get("field_stats", {}), "preview_urls": urls}


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
