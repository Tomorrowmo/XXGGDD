"""工况对齐服务 —— 评估模型的心脏（docs/02 §3）。

各单位工况标识不一定一致，全部收敛到平台统一的 canonical_key；
对不上的落 PENDING 进人工待办。对齐动作本身带方法与置信度，可追溯、可纠偏。
"""
from __future__ import annotations

import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    OperatingPoint, CaseOperatingLink, Case, MapMethod, Confidence,
)


def canonical_key_from_params(params: dict | None) -> str | None:
    """由工况物理参数推出规范键，如 {Ma:6.0, dyn_pressure_kpa:60} → 'Ma6-60kPa'。"""
    if not params:
        return None
    ma = params.get("Ma") or params.get("mach") or params.get("mach_number")
    q = params.get("dyn_pressure_kpa") or params.get("dynamic_pressure") or params.get("q_kpa")
    if ma is None:
        return None
    ma_s = f"Ma{float(ma):g}"
    if q is not None:
        return f"{ma_s}-{int(round(float(q)))}kPa"
    return ma_s


def canonical_key_from_name(name: str) -> str | None:
    """从算例/车次名里正则抠工况（rule 对齐），如 'Ma6-60kPa' / 'Ma6_60k'。"""
    m = re.search(r"Ma\s*([\d.]+)[-_ ]*([\d.]+)\s*k", name, re.IGNORECASE)
    if m:
        return f"Ma{float(m.group(1)):g}-{int(round(float(m.group(2))))}kPa"
    m = re.search(r"Ma\s*([\d.]+)", name, re.IGNORECASE)
    if m:
        return f"Ma{float(m.group(1)):g}"
    return None


def get_or_create_op(db: Session, canonical_key: str, params: dict | None = None) -> OperatingPoint:
    op = db.execute(
        select(OperatingPoint).where(OperatingPoint.canonical_key == canonical_key)
    ).scalar_one_or_none()
    if op is None:
        op = OperatingPoint(canonical_key=canonical_key, params=params or {})
        db.add(op)
        db.flush()
    elif params and not op.params:
        op.params = params
    return op


def align_case(db: Session, case: Case, params: dict | None = None) -> CaseOperatingLink:
    """把算例对齐到规范工况：先 auto（参数）→ rule（名字）→ 都不行落 PENDING。"""
    key = canonical_key_from_params(params)
    method, conf = MapMethod.AUTO, Confidence.HIGH
    if key is None:
        key = canonical_key_from_name(case.name)
        method, conf = MapMethod.RULE, Confidence.MED
    if key is None:
        # 对不上 → PENDING 待人工（挂占位 OP，等人工改派）
        link = CaseOperatingLink(case_id=case.id, op_id=_pending_op(db).id,
                                 method=MapMethod.AUTO, mapping_confidence=Confidence.PENDING,
                                 mapped_by="system")
        db.add(link)
        db.flush()
        return link

    op = get_or_create_op(db, key, params)
    link = CaseOperatingLink(case_id=case.id, op_id=op.id, method=method,
                             mapping_confidence=conf, mapped_by="system")
    db.add(link)
    db.flush()
    return link


def _pending_op(db: Session) -> OperatingPoint:
    """未识别工况的占位 OP（所有 PENDING 项挂这里，等人工改派）。"""
    return get_or_create_op(db, "__UNALIGNED__", {"note": "工况未识别，待人工指定"})


def assign_op_manual(db: Session, link: CaseOperatingLink, canonical_key: str,
                     params: dict | None = None, user: str = "user") -> CaseOperatingLink:
    """人工为 PENDING 项指定工况。"""
    op = get_or_create_op(db, canonical_key, params)
    link.op_id = op.id
    link.method = MapMethod.MANUAL
    link.mapping_confidence = Confidence.HIGH
    link.mapped_by = user
    db.flush()
    return link
