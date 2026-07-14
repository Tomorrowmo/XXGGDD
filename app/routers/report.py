"""评估报告 API（v2）+ 种子数据。"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from app.db import get_db
from app.services.evaluation import build_report
from app.services import seed as seed_svc

router = APIRouter(prefix="/api/v2", tags=["report"])


@router.get("/report/{op_key}")
def get_report(op_key: str, engine: str = "XF-2 双模态冲压发动机", db: Session = Depends(get_db)):
    """生成某工况的五段式评估报告。"""
    return build_report(db, op_key, engine_name=engine)


@router.get("/report/{op_key}/export", response_class=PlainTextResponse)
def export_report(op_key: str, engine: str = "XF-2 双模态冲压发动机", db: Session = Depends(get_db)):
    """导出 Markdown 格式报告（可另存/追加知识库）。"""
    rep = build_report(db, op_key, engine_name=engine)
    if not rep.get("ok"):
        return f"# 报告生成失败\n\n{rep.get('reason', '')}"
    s = rep["sections"]
    lines = [f"# {rep['title']}", "", f"> 参照 {rep['truth_source']}（实验真值）", ""]
    lines += ["## 一、评估范围", s["评估范围"], ""]
    lines += ["## 二、各物理量偏差"] + [f"- {x}" for x in s["各物理量偏差"]] + [""]
    lines += ["## 三、专家结论"] + [f"- {x}" for x in s["专家结论"]] + [""]
    lines += ["## 四、评级与建议", s["评级与建议"], ""]
    return "\n".join(lines)


@router.post("/seed")
def seed_demo(reset: bool = False, db: Session = Depends(get_db)):
    """写入 XF-2 Ma6-60kPa 演示场景（联调用）。"""
    return seed_svc.seed(db, reset=reset)
