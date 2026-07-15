"""数据资源库 API（v2）—— 批量入库 / 分层浏览 / 详情 / 切片 / PENDING 人工对齐。"""
from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from app.db import get_db
from app.db.database import SessionLocal
from app.db.models import (
    Unit, Delivery, Case, CaseOperatingLink, OperatingPoint, Measurement,
    Confidence, CaseKind,
)
from app.services import ingest as ingest_svc
from app.services import operating_point as op_svc
from app.services import viz

router = APIRouter(prefix="/api/v2", tags=["library"])

SSE_HEADERS = {"Cache-Control": "no-cache, no-transform",
               "X-Accel-Buffering": "no", "Connection": "keep-alive"}


# ------------------------------------------------------------------ 入库
class IngestFileReq(BaseModel):
    path: str
    unit_name: str
    delivery_label: str = "默认交付"


class IngestDirReq(BaseModel):
    directory: str
    unit_name: str
    delivery_label: str = "默认交付"


@router.post("/ingest/file")
def ingest_file(req: IngestFileReq, db: Session = Depends(get_db)):
    return ingest_svc.ingest_file(db, req.path, unit_name=req.unit_name,
                                  delivery_label=req.delivery_label)


@router.post("/ingest/dir")
def ingest_dir(req: IngestDirReq, db: Session = Depends(get_db)):
    return ingest_svc.ingest_directory(db, req.directory, unit_name=req.unit_name,
                                       delivery_label=req.delivery_label)


@router.post("/ingest/file/stream")
def ingest_file_stream(req: IngestFileReq):
    """流式入库：实时推送 识别→去重→解析→对齐→写库→切片 各步骤进度（SSE）。

    用独立 SessionLocal（流式生成器在请求会话关闭后仍运行），末尾发 result 事件。
    """
    def gen():
        s = SessionLocal()
        try:
            for kind_, payload in ingest_svc.ingest_steps(
                    s, req.path, unit_name=req.unit_name,
                    delivery_label=req.delivery_label, with_slices=True):
                tag = "result" if kind_ == "result" else "progress"
                yield f"data: {json.dumps({'type': tag, **payload}, ensure_ascii=False)}\n\n"
        except Exception as e:  # noqa: BLE001
            yield f"data: {json.dumps({'type': 'result', 'ok': False, 'reason': str(e)[:200]}, ensure_ascii=False)}\n\n"
        finally:
            s.close()
        yield "data: [DONE]\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream", headers=SSE_HEADERS)


# ------------------------------------------------------------------ 浏览
@router.get("/units")
def list_units(db: Session = Depends(get_db)):
    units = db.execute(select(Unit)).scalars().all()
    out = []
    for u in units:
        n_cases = db.execute(
            select(func.count(Case.id)).join(Delivery).where(Delivery.unit_id == u.id)
        ).scalar_one()
        out.append({"id": u.id, "name": u.name, "type": u.type,
                    "deliveries": [{"id": d.id, "label": d.label} for d in u.deliveries],
                    "n_cases": n_cases})
    return {"units": out}


def _case_brief(db: Session, c: Case) -> dict:
    link = db.execute(
        select(CaseOperatingLink).where(CaseOperatingLink.case_id == c.id)
    ).scalar_one_or_none()
    op_key = None
    if link and link.op_id:
        op = db.get(OperatingPoint, link.op_id)
        op_key = op.canonical_key if op else None
    unit = c.delivery.unit
    return {
        "id": c.id, "name": c.name, "kind": c.kind.value,
        "unit": unit.name, "delivery": c.delivery.label,
        "source_format": c.source_format,
        "operating_point": op_key,
        "parse_confidence": c.parse_confidence.value,
        "mapping_confidence": link.mapping_confidence.value if link else None,
        "context": c.context,
    }


@router.get("/cases")
def list_cases(unit: str | None = None, kind: str | None = None,
               op: str | None = None, db: Session = Depends(get_db)):
    q = select(Case)
    cases = db.execute(q).scalars().all()
    out = []
    for c in cases:
        b = _case_brief(db, c)
        if unit and b["unit"] != unit:
            continue
        if kind and b["kind"] != kind:
            continue
        if op and b["operating_point"] != op:
            continue
        out.append(b)
    return {"cases": out}


@router.get("/cases/{case_id}")
def case_detail(case_id: int, db: Session = Depends(get_db)):
    c = db.get(Case, case_id)
    if c is None:
        raise HTTPException(404, "算例不存在")
    brief = _case_brief(db, c)
    meas = db.execute(select(Measurement).where(Measurement.case_id == case_id)).scalars().all()
    brief["measurements"] = [
        {"quantity": m.quantity.physical_name, "value": m.value, "unit": m.unit,
         "confidence": m.confidence.value, "status": m.status, "evidence": m.evidence}
        for m in meas
    ]
    return brief


@router.get("/cases/{case_id}/thumbnail")
def case_thumbnail(case_id: int, db: Session = Depends(get_db)):
    """列表缩略图：仅返回**已缓存**的切片（不触发渲染，保证列表加载快）。

    偏好带体信息的视角（surf_a → slice_Z → 任一）；无缓存则 available=False，前端回退占位图。
    """
    c = db.get(Case, case_id)
    if c is None:
        raise HTTPException(404, "算例不存在")
    if c.kind != CaseKind.SIMULATION:
        return {"available": False, "reason": "仅仿真算例有切片缩略图"}
    res = viz.cached_previews(c.storage_uri)
    imgs = res.get("images", {})
    if not imgs:
        return {"available": False}
    key = Path(res["dir"]).name
    pick = next((n for n in ("surf_a", "slice_Z", "slice_X", "surf_b") if n in imgs),
                next(iter(imgs)))
    return {"available": True, "url": f"/previews/{key}/{imgs[pick]}", "which": pick}


@router.get("/cases/{case_id}/previews")
def case_previews(case_id: int, db: Session = Depends(get_db)):
    c = db.get(Case, case_id)
    if c is None:
        raise HTTPException(404, "算例不存在")
    if c.kind != CaseKind.SIMULATION:
        return {"available": False, "reason": "仅仿真算例有切片快照"}
    res = viz.generate_previews(c.storage_uri)
    # 把绝对目录转成 /previews 静态 URL 供前端加载
    if res.get("available") and res.get("dir"):
        key = Path(res["dir"]).name
        res["urls"] = {name: f"/previews/{key}/{fn}" for name, fn in res.get("images", {}).items()}
    return res


# ------------------------------------------------------------------ PENDING 人工对齐
@router.get("/pending")
def list_pending(db: Session = Depends(get_db)):
    links = db.execute(
        select(CaseOperatingLink).where(
            CaseOperatingLink.mapping_confidence == Confidence.PENDING)
    ).scalars().all()
    out = []
    for lk in links:
        c = db.get(Case, lk.case_id)
        out.append({"link_id": lk.id, "case_id": c.id, "name": c.name,
                    "unit": c.delivery.unit.name})
    return {"pending": out}


@router.get("/operating-points")
def list_operating_points(db: Session = Depends(get_db)):
    """已有工况列表（供人工对齐下拉，选已有=保证 canonical_key 一致）。"""
    ops = db.execute(select(OperatingPoint)).scalars().all()
    out = []
    for op in ops:
        if op.canonical_key == "__UNALIGNED__":
            continue
        n = db.execute(
            select(func.count(CaseOperatingLink.id)).where(
                CaseOperatingLink.op_id == op.id,
                CaseOperatingLink.mapping_confidence != Confidence.PENDING)
        ).scalar_one()
        out.append({"canonical_key": op.canonical_key, "params": op.params or {}, "n_cases": n})
    out.sort(key=lambda x: x["canonical_key"])
    return {"operating_points": out}


class PreviewKeyReq(BaseModel):
    params: dict


@router.post("/operating-points/preview-key")
def preview_key(req: PreviewKeyReq):
    """由结构化参数预览规范键（前端填 Ma/动压/攻角时实时显示）。"""
    key = op_svc.canonical_key_from_params(req.params)
    return {"canonical_key": key, "ok": key is not None,
            "reason": None if key else "至少需要马赫数 Ma"}


class AssignOpReq(BaseModel):
    canonical_key: str | None = None
    params: dict | None = None


@router.post("/links/{link_id}/assign-op")
def assign_op(link_id: int, req: AssignOpReq, db: Session = Depends(get_db)):
    lk = db.get(CaseOperatingLink, link_id)
    if lk is None:
        raise HTTPException(404, "对齐记录不存在")
    # 优先用显式 canonical_key（选已有）；否则由结构化参数推导（新建）
    key = (req.canonical_key or "").strip() or op_svc.canonical_key_from_params(req.params)
    if not key:
        raise HTTPException(400, "需指定工况：选已有 canonical_key，或提供含 Ma 的结构化参数")
    op_svc.assign_op_manual(db, lk, key, req.params)
    db.commit()
    return {"ok": True, "op": key}
