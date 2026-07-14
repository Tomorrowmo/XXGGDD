"""自然语言检索服务 —— NL → 结构化查询（over 评估元数据）。

对齐原型顶栏检索：把大白话解析成对 单位/工况/类型/置信度/判据 的过滤条件，
返回命中算例 + 结构化条件（NL2SQL 的轻量版；后续可换 LLM/NL2Cypher）。
"""
from __future__ import annotations

import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    Unit, Case, CaseOperatingLink, OperatingPoint, Confidence, CaseKind,
)
from app.services.evaluation import assemble_compare


def _brief(db: Session, c: Case) -> dict:
    link = db.execute(
        select(CaseOperatingLink).where(CaseOperatingLink.case_id == c.id)
    ).scalar_one_or_none()
    op_key = None
    conf = None
    if link:
        conf = link.mapping_confidence.value
        if link.op_id:
            op = db.get(OperatingPoint, link.op_id)
            op_key = op.canonical_key if op else None
    return {"id": c.id, "name": c.name, "unit": c.delivery.unit.name,
            "kind": c.kind.value, "operating_point": op_key,
            "mapping_confidence": conf, "parse_confidence": c.parse_confidence.value}


def parse_query(db: Session, q: str) -> list[dict]:
    """把 NL 解析成结构化条件 [{field,label,value}]。"""
    conds: list[dict] = []
    # 单位
    for u in db.execute(select(Unit)).scalars().all():
        if u.name in q:
            conds.append({"field": "unit", "label": "单位", "value": u.name})
    # 工况
    m = re.search(r"Ma\s*[\d.]+(?:[-_ ]*\d+\s*k[Pp]?a?)?", q)
    if m:
        conds.append({"field": "op", "label": "工况", "value": m.group(0).replace(" ", "")})
    # 类型
    if "仿真" in q:
        conds.append({"field": "kind", "label": "类型", "value": "simulation"})
    if "实验" in q or "试车" in q:
        conds.append({"field": "kind", "label": "类型", "value": "experiment"})
    # 状态/置信度
    if re.search(r"未对齐|待对齐|pending|待人工", q, re.IGNORECASE):
        conds.append({"field": "pending", "label": "状态", "value": "PENDING"})
    # 意图
    if re.search(r"越界|超范围|超限", q):
        conds.append({"field": "intent", "label": "判据", "value": "越界"})
    if re.search(r"偏差最小|最优|最准|哪家.*(好|优|准)", q):
        conds.append({"field": "intent", "label": "聚合", "value": "偏差排序"})
    return conds


def search(db: Session, q: str) -> dict:
    """执行检索：返回 {conditions, results, answer?}。"""
    conds = parse_query(db, q)
    fields = {c["field"]: c["value"] for c in conds}

    # 聚合意图：偏差排序 → 直接给排名答案
    if fields.get("intent") == "偏差排序":
        op_key = fields.get("op", "Ma6-60kPa")
        res = assemble_compare(db, op_key)
        if res:
            rank = [{"unit": r.unit, "case": r.case, "avg_deviation": r.avg_deviation,
                     "grade": r.grade, "rank": r.rank} for r in res.ranking]
            return {"conditions": conds, "answer_type": "ranking",
                    "answer": rank, "results": []}

    # 过滤算例
    cases = db.execute(select(Case)).scalars().all()
    briefs = [_brief(db, c) for c in cases]
    out = []
    for b in briefs:
        if "unit" in fields and b["unit"] != fields["unit"]:
            continue
        if "kind" in fields and b["kind"] != fields["kind"]:
            continue
        if "op" in fields and b["operating_point"] != fields["op"]:
            continue
        if "pending" in fields and b["mapping_confidence"] != "PENDING":
            continue
        out.append(b)

    # 越界意图：过滤出该工况下有 >10% 偏差的仿真单位
    if fields.get("intent") == "越界":
        op_key = fields.get("op", "Ma6-60kPa")
        res = assemble_compare(db, op_key)
        over_units = set()
        if res:
            for row in res.rows:
                for s in row.sources:
                    if abs(s["deviation_pct"]) > 10:
                        over_units.add(s["unit"])
        out = [b for b in out if b["kind"] == "simulation" and b["unit"] in over_units]

    return {"conditions": conds, "answer_type": "cases", "results": out}
