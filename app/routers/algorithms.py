"""用户自定义算法 skills API（v2）—— 表达式编排：增删/校验/在真实算例上试算。

变量上下文 = 算例落库的测量（QOI/关键量，按 quantity.key）+ 物理常数（gamma/R）。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.db.models import Case, Measurement, Quantity
from app.services import algorithms as algo
from app.settings import settings

router = APIRouter(prefix="/api/v2/algorithms", tags=["algorithms"])


def _case_context(db: Session, case_id: int) -> dict:
    """算例可用变量上下文：落库测量（按 quantity.key）+ 物理常数。"""
    ctx: dict[str, float] = {"gamma": settings.physics.gamma, "R": settings.physics.gas_constant}
    for m in db.execute(select(Measurement).where(Measurement.case_id == case_id)).scalars().all():
        q = db.get(Quantity, m.quantity_id)
        if q and isinstance(m.value, (int, float)):
            ctx[q.key] = float(m.value)
    return ctx


@router.get("")
def list_algos():
    return {"algorithms": algo.list_algorithms()}


class AddReq(BaseModel):
    name: str
    expr: str
    unit: str = ""
    category: str = "自定义"
    description: str = ""


@router.post("")
def add_algo(req: AddReq):
    try:
        return algo.add_algorithm(name=req.name, expr=req.expr, unit=req.unit,
                                  category=req.category, description=req.description)
    except algo.ExprError as e:
        raise HTTPException(400, str(e))


@router.delete("/{algo_id}")
def del_algo(algo_id: str):
    return {"ok": algo.delete_algorithm(algo_id)}


class ValidateReq(BaseModel):
    expr: str


@router.post("/validate")
def validate(req: ValidateReq):
    return algo.validate_expr(req.expr)


@router.get("/case-context/{case_id}")
def case_context(case_id: int, db: Session = Depends(get_db)):
    """列出某算例可用于表达式的变量及当前值（供前端提示 + 试算）。"""
    c = db.get(Case, case_id)
    if c is None:
        raise HTTPException(404, "算例不存在")
    ctx = _case_context(db, case_id)
    return {"case": c.name, "vars": [{"name": k, "value": round(v, 6)} for k, v in sorted(ctx.items())]}


class EvalReq(BaseModel):
    expr: str
    case_id: int


@router.post("/eval")
def eval_on_case(req: EvalReq, db: Session = Depends(get_db)):
    """在指定算例的真实变量上下文上求值（试算/应用）。"""
    if db.get(Case, req.case_id) is None:
        raise HTTPException(404, "算例不存在")
    return algo.evaluate(req.expr, _case_context(db, req.case_id))
