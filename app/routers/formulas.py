"""公式库目录 API（v2）—— 列出可用计算公式（skills），供专业分析页/文档展示与扩展。"""
from __future__ import annotations

from fastapi import APIRouter

from app.services.formulas.catalog import catalog_public

router = APIRouter(prefix="/api/v2/formulas", tags=["formulas"])


@router.get("")
def list_formulas():
    """按类别列出公式库全部公式（表达式/输入/输出/单位/文献）。"""
    items = catalog_public()
    cats: dict[str, list] = {}
    for it in items:
        cats.setdefault(it["category"], []).append(it)
    return {"n": len(items), "categories": [{"name": k, "formulas": v} for k, v in cats.items()]}
