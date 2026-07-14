"""单对象分析 API（v2）—— 仿真/试验详情的真实数据（供仿真分析/试验分析屏）。

数据来自算例的真实文件：试验走可配置解析，仿真走 simparse。种子数据无文件→available=False。
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.db.models import Case, CaseKind
from app.services import experiment as exp_svc
from app.services import criteria as crit_svc
from app.services import simparse_adapter, viz

router = APIRouter(prefix="/api/v2/cases", tags=["analysis"])


def _downsample(x: np.ndarray, y: np.ndarray, n: int = 400):
    if len(x) <= n:
        return x, y
    idx = np.linspace(0, len(x) - 1, n).astype(int)
    return x[idx], y[idx]


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
