"""对比评估 API（v2）—— 从库里测量按工况组装，跑多源对比评分。"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.services.compare import compare_result_to_dict
from app.services.evaluation import assemble_compare

router = APIRouter(prefix="/api/v2/compare", tags=["compare"])


@router.get("/operating-point/{op_key}")
def compare_op(op_key: str, db: Session = Depends(get_db)):
    """对比某工况：实验测量为真值，各单位仿真测量为待评源，按物理量算偏差+排名。"""
    res = assemble_compare(db, op_key)
    if res is None:
        return {"operating_point": op_key, "rows": [], "ranking": [],
                "reason": "该工况缺实验真值或仿真源，无法对比"}
    return compare_result_to_dict(res)
