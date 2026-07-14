"""种子数据 —— 把原型的 XF-2 Ma6-60kPa 评估场景写进库。

用于演示/联调：3 家仿真单位 + 1 试车台真值，对齐同一工况，产出可评估的完整数据。
代表"入库+simparse+试验解析"最终应产出的结构，前端接 v2 API 后即有真实数据可展示。
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    Unit, Delivery, Case, Quantity, Measurement, CaseOperatingLink,
    CaseKind, ParseStatus, Confidence, MapMethod,
)
from app.services.operating_point import get_or_create_op

# 物理量登记：key, 名称, 量纲
QUANTITIES = [
    ("wall_p_22", "流道22壁压峰值", "MPa"),
    ("wall_p_24", "流道24壁压峰值", "MPa"),
    ("chamber_p", "燃烧室压力", "MPa"),
    ("isolator_ratio", "隔离段出口压比", ""),
    ("thrust", "推力", "kN"),
    ("isp", "比冲", "s"),
    ("comb_eff", "燃烧效率", ""),
    ("pt_recovery", "总压恢复系数", ""),
]

# 实验真值（试车03）
TRUTH = {
    "wall_p_22": 3.20, "wall_p_24": 3.48, "chamber_p": 2.10, "isolator_ratio": 4.85,
    "thrust": 48.5, "isp": 342, "comb_eff": 0.965, "pt_recovery": 0.420,
}

# 各单位仿真值：unit, delivery, case, context, {qkey: value}
SIM_CASES = [
    ("西工大", "2026Q1 一轮交付", "case4",
     {"solver": "密度基 k-ω SST", "mesh_cells": 12_000_000, "y_plus": 35, "converged": True},
     {"wall_p_22": 3.28, "wall_p_24": 3.52, "chamber_p": 2.13, "isolator_ratio": 4.79,
      "thrust": 47.9, "isp": 345, "comb_eff": 0.958, "pt_recovery": 0.416}),
    ("航天六院", "2026Q1 交付", "caseZ",
     {"solver": "密度基 k-ε RLZ", "mesh_cells": 8_000_000, "y_plus": 55, "converged": True},
     {"wall_p_22": 3.31, "wall_p_24": 3.57, "chamber_p": 2.16, "isolator_ratio": 4.71,
      "thrust": 47.2, "isp": 338, "comb_eff": 0.949, "pt_recovery": 0.408}),
    ("北航", "2026Q1 交付", "caseX",
     {"solver": "压力基 k-ε", "mesh_cells": 6_400_000, "y_plus": 88, "converged": True},
     {"wall_p_22": 3.55, "wall_p_24": 3.86, "chamber_p": 2.31, "isolator_ratio": 5.34,
      "thrust": 43.1, "isp": 361, "comb_eff": 0.910, "pt_recovery": 0.373}),
]

OP_KEY = "Ma6-60kPa"
OP_PARAMS = {"Ma": 6.0, "dyn_pressure_kpa": 60, "total_temp_k": 1650,
             "total_pressure_mpa": 2.5, "fuel": "煤油", "equivalence_ratio": 0.80}


def _unit(db, name, typ="承研单位"):
    u = db.execute(select(Unit).where(Unit.name == name)).scalar_one_or_none()
    if not u:
        u = Unit(name=name, type=typ); db.add(u); db.flush()
    return u


def _delivery(db, unit, label):
    d = db.execute(select(Delivery).where(Delivery.unit_id == unit.id,
                                          Delivery.label == label)).scalar_one_or_none()
    if not d:
        d = Delivery(unit_id=unit.id, label=label); db.add(d); db.flush()
    return d


def _quantity(db, key, name, unit_dim):
    q = db.execute(select(Quantity).where(Quantity.key == key)).scalar_one_or_none()
    if not q:
        q = Quantity(key=key, physical_name=name, standard_unit=unit_dim); db.add(q); db.flush()
    return q


def seed(db: Session, *, reset: bool = False) -> dict:
    """写入 XF-2 场景。已存在则跳过（除非 reset）。"""
    existing = db.execute(select(Case).where(Case.name == "case4")).scalar_one_or_none()
    if existing and not reset:
        return {"ok": True, "seeded": False, "reason": "已存在，跳过"}

    op = get_or_create_op(db, OP_KEY, OP_PARAMS)
    quantities = {k: _quantity(db, k, n, u) for k, n, u in QUANTITIES}

    def link_case(case: Case, conf: Confidence):
        db.add(CaseOperatingLink(case_id=case.id, op_id=op.id, method=MapMethod.AUTO,
                                 mapping_confidence=conf, mapped_by="seed"))

    # 试车台真值
    tt = _unit(db, "试车台", "试车台")
    td = _delivery(db, tt, "2026Q1")
    trial = Case(delivery_id=td.id, kind=CaseKind.EXPERIMENT, name="试车03",
                 source_format="txt-experiment", storage_uri="(seed)",
                 content_hash="seed-trial03", parse_status=ParseStatus.PARSED,
                 parse_confidence=Confidence.HIGH, context={"channels": 28, "n_rows": 18412})
    db.add(trial); db.flush()
    link_case(trial, Confidence.HIGH)
    for k, name, unit_dim in QUANTITIES:
        db.add(Measurement(case_id=trial.id, op_id=op.id, quantity_id=quantities[k].id,
                           value=TRUTH[k], unit=unit_dim, raw_name=name,
                           source_kind=CaseKind.EXPERIMENT, status="normal",
                           confidence=Confidence.HIGH, evidence={"method": "稳态段/峰值"}))

    # 各单位仿真
    for unit_name, dlabel, cname, ctx, vals in SIM_CASES:
        u = _unit(db, unit_name)
        d = _delivery(db, u, dlabel)
        conf = Confidence.HIGH if ctx["mesh_cells"] >= 8_000_000 else Confidence.MED
        c = Case(delivery_id=d.id, kind=CaseKind.SIMULATION, name=cname,
                 source_format="fluent-hdf5", storage_uri=f"(seed)/{cname}",
                 content_hash=f"seed-{cname}", parse_status=ParseStatus.PARSED,
                 parse_confidence=conf, context=ctx)
        db.add(c); db.flush()
        link_case(c, conf)
        for k, name, unit_dim in QUANTITIES:
            db.add(Measurement(case_id=c.id, op_id=op.id, quantity_id=quantities[k].id,
                               value=vals[k], unit=unit_dim, raw_name=name,
                               source_kind=CaseKind.SIMULATION, status="normal",
                               confidence=conf, evidence={"solver": ctx["solver"]}))

    db.commit()
    return {"ok": True, "seeded": True, "operating_point": OP_KEY,
            "units": 4, "cases": 4, "quantities": len(QUANTITIES)}
