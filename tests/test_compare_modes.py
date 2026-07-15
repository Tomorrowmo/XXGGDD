"""对比评估两模式：有真值→truth；无真值多家仿真→consensus（多源交叉）。"""
from sqlalchemy import select

from app.db.database import SessionLocal
from app.db.models import (
    Unit, Delivery, Case, Quantity, Measurement, CaseOperatingLink,
    CaseKind, ParseStatus, Confidence, MapMethod,
)
from app.services.compare import cross_compare, SourceValue
from app.services.evaluation import assemble_evaluation
from app.services.operating_point import get_or_create_op


def test_cross_compare_math():
    q = [{"quantity": "推力", "unit_dim": "kN",
          "sources": [SourceValue("A", "a", 100.0), SourceValue("B", "b", 110.0),
                      SourceValue("C", "c", 90.0)]}]
    d = cross_compare("op", q)
    assert d["mode"] == "consensus"
    row = d["rows"][0]
    assert row["mean"] == 100.0
    # C 和 B 离均值 10%，A=100 正好在均值
    devs = {s["unit"]: s["deviation_pct"] for s in row["sources"]}
    assert devs["A"] == 0.0 and abs(devs["B"] - 10.0) < 1e-6 and abs(devs["C"] + 10.0) < 1e-6
    assert d["consensus"][0]["unit"] == "A"     # A 最贴近共识


def test_truth_mode_from_seed(seeded_db):
    d = assemble_evaluation(seeded_db, "Ma6-60kPa")
    assert d["mode"] == "truth"
    assert len(d["ranking"]) == 3 and d["truth_source"]


def _sim_case(s, unit_name, op, cname, vals):
    u = s.execute(select(Unit).where(Unit.name == unit_name)).scalar_one_or_none() or Unit(name=unit_name, type="承研单位")
    if u.id is None:
        s.add(u); s.flush()
    d = Delivery(unit_id=u.id, label="Q"); s.add(d); s.flush()
    c = Case(delivery_id=d.id, kind=CaseKind.SIMULATION, name=cname, source_format="cgns",
             storage_uri="(t)", content_hash="h-" + cname, parse_status=ParseStatus.PARSED,
             parse_confidence=Confidence.HIGH, context={})
    s.add(c); s.flush()
    s.add(CaseOperatingLink(case_id=c.id, op_id=op.id, method=MapMethod.MANUAL,
                            mapping_confidence=Confidence.HIGH, mapped_by="t"))
    for k, v in vals.items():
        q = s.execute(select(Quantity).where(Quantity.key == k)).scalar_one_or_none() or Quantity(key=k, physical_name=k, standard_unit="")
        if q.id is None:
            s.add(q); s.flush()
        s.add(Measurement(case_id=c.id, op_id=op.id, quantity_id=q.id, value=v, unit="",
                          raw_name=k, source_kind=CaseKind.SIMULATION, status="normal",
                          confidence=Confidence.HIGH, evidence={}))


def test_consensus_mode_no_truth(db):
    op = get_or_create_op(db, "Ma3-AoA5", {"Ma": 3, "aoa": 5})
    _sim_case(db, "甲", op, "s1", {"Cd": 0.30, "Cl": 1.0})
    _sim_case(db, "乙", op, "s2", {"Cd": 0.32, "Cl": 1.1})
    _sim_case(db, "丙", op, "s3", {"Cd": 0.55, "Cl": 1.05})   # Cd 离群
    db.commit()
    d = assemble_evaluation(db, "Ma3-AoA5")
    assert d["mode"] == "consensus"
    assert d["n_units"] == 3 and d["n_quantities"] == 2
    # 丙 的 Cd 明显偏高 → 应是离群或离共识最远
    assert d["consensus"][-1]["unit"] == "丙"
