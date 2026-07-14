"""评估编排（DB 感知）—— 从库里测量装配多源对比，并生成评估报告。

compare 路由与 report 路由共用此处，避免装配逻辑重复。
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    OperatingPoint, CaseOperatingLink, Case, Measurement, Quantity, CaseKind,
)
from app.services.compare import (
    compare_operating_point, compare_result_to_dict, SourceValue, CompareResult,
)


def assemble_compare(db: Session, op_key: str) -> CompareResult | None:
    """把某工况下的库内测量装配成对比输入并评分。无数据返回 None。"""
    op = db.execute(
        select(OperatingPoint).where(OperatingPoint.canonical_key == op_key)
    ).scalar_one_or_none()
    if op is None:
        return None
    links = db.execute(
        select(CaseOperatingLink).where(CaseOperatingLink.op_id == op.id)
    ).scalars().all()
    case_ids = [lk.case_id for lk in links]
    if not case_ids:
        return None

    truth_source = None
    agg: dict[str, dict] = {}
    for cid in case_ids:
        case = db.get(Case, cid)
        unit = case.delivery.unit.name
        for m in db.execute(select(Measurement).where(Measurement.case_id == cid)).scalars().all():
            q = db.get(Quantity, m.quantity_id)
            slot = agg.setdefault(q.key, {"name": q.physical_name, "unit": m.unit,
                                          "truth": None, "sources": []})
            if m.source_kind == CaseKind.EXPERIMENT:
                slot["truth"] = m.value
                truth_source = case.name
            else:
                slot["sources"].append(SourceValue(unit=unit, case=case.name, value=m.value))

    quantities = [
        {"quantity": v["name"], "unit_dim": v["unit"], "truth": v["truth"], "sources": v["sources"]}
        for v in agg.values() if v["truth"] is not None and v["sources"]
    ]
    if not quantities:
        return None
    return compare_operating_point(op_key, truth_source or "实验", quantities)


def build_report(db: Session, op_key: str, engine_name: str = "被评发动机") -> dict:
    """由对比结果生成五段式评估报告（对齐原型评估报告页）。"""
    res = assemble_compare(db, op_key)
    if res is None:
        return {"ok": False, "reason": f"工况 {op_key} 无足够数据生成报告"}
    d = compare_result_to_dict(res)
    ranking = d["ranking"]
    winner = ranking[0] if ranking else None

    # 逐项偏差要点
    dev_points = []
    for row in d["rows"]:
        parts = [f"{s['unit']} {s['deviation_pct']:+.1f}%" for s in row["sources"]]
        dev_points.append(f"{row['quantity']}：" + " / ".join(parts))

    # 专家结论（确定性汇总；部署机可再由 agent「渊」增强）
    concl = []
    for r in ranking:
        verdict = "可信" if r["avg_deviation"] <= 3 else ("需复核" if r["avg_deviation"] <= 10 else "存疑")
        concl.append(f"{r['unit']} {r['case']}：平均偏差 {r['avg_deviation']}%、{r['n_pass']}/{r['n_total']} 达标 → {verdict}（{r['grade']}）")

    rank_str = " > ".join(f"{r['unit']} {r['grade']}" for r in ranking)
    return {
        "ok": True,
        "title": f"{op_key} 工况 · {engine_name} 多源仿真数据评估报告",
        "operating_point": op_key,
        "truth_source": d["truth_source"],
        "sections": {
            "评估范围": f"针对 {op_key} 工况，对 {len(ranking)} 家仿真交付，以 {d['truth_source']}（实验真值）为参照，比对 {len(d['rows'])} 项 QOI。",
            "各物理量偏差": dev_points,
            "专家结论": concl,
            "评级与建议": f"综合排名：{rank_str}。" + (f"建议末位单位复核边界条件后重交付。" if len(ranking) > 1 else ""),
        },
        "ranking": ranking,
        "rows": d["rows"],
    }
