"""对比评估 API（v2）—— 从库里测量按工况组装，跑多源对比评分。"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.services.evaluation import assemble_evaluation

router = APIRouter(prefix="/api/v2/compare", tags=["compare"])


@router.get("/operating-point/{op_key}")
def compare_op(op_key: str, db: Session = Depends(get_db)):
    """对比某工况：有实验真值→真值模式(逐项偏差+排名评级)；
    无真值但有多家仿真→多源交叉对比(共识均值/离散度/离群)。"""
    d = assemble_evaluation(db, op_key)
    if d is None:
        return {"operating_point": op_key, "rows": [], "ranking": [], "mode": "none",
                "reason": "该工况下无可对比数据（需同工况既有实验真值+仿真，或≥2 家仿真）"}
    return d
