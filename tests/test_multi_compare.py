"""多算例 / 多车次对比端点测试（sim-compare / exp-compare）。

数据源统一为库内 Measurement（对种子与真实入库一致），故用种子 + 追加一条
重复试验车次来覆盖：网格无关性偏差、重复性 CV / 离群车次。
"""
from sqlalchemy import select

from app.db.database import SessionLocal
from app.db.models import (
    Unit, Delivery, Case, Quantity, Measurement, CaseOperatingLink,
    CaseKind, ParseStatus, Confidence, MapMethod,
)


def _ids_by_kind(client, kind: str) -> list[int]:
    cases = client.get("/api/v2/cases").json()["cases"]
    return [c["id"] for c in cases if c["kind"] == kind]


def _add_experiment_run(name: str, values: dict[str, float]) -> int:
    """在种子库里追加一个同工况试验车次（复用 seed 的量登记 + 试车台单位）。"""
    s = SessionLocal()
    try:
        unit = s.execute(select(Unit).where(Unit.name == "试车台")).scalar_one()
        deliv = s.execute(select(Delivery).where(Delivery.unit_id == unit.id)).scalars().first()
        link = s.execute(select(CaseOperatingLink)).scalars().first()
        op_id = link.op_id
        c = Case(delivery_id=deliv.id, kind=CaseKind.EXPERIMENT, name=name,
                 source_format="txt-experiment", storage_uri="(test)",
                 content_hash=f"test-{name}", parse_status=ParseStatus.PARSED,
                 parse_confidence=Confidence.HIGH, context={"channels": 28, "n_rows": 18000})
        s.add(c); s.flush()
        s.add(CaseOperatingLink(case_id=c.id, op_id=op_id, method=MapMethod.AUTO,
                                mapping_confidence=Confidence.HIGH, mapped_by="test"))
        for key, val in values.items():
            q = s.execute(select(Quantity).where(Quantity.key == key)).scalar_one()
            s.add(Measurement(case_id=c.id, op_id=op_id, quantity_id=q.id, value=val,
                              unit=q.standard_unit, raw_name=q.physical_name,
                              source_kind=CaseKind.EXPERIMENT, status="normal",
                              confidence=Confidence.HIGH, evidence={"method": "test"}))
        s.commit()
        return c.id
    finally:
        s.close()


# --------------------------------------------------------------------- sim-compare
def test_sim_compare_needs_two(client):
    client.post("/api/v2/seed")
    sims = _ids_by_kind(client, "simulation")
    d = client.get(f"/api/v2/cases/sim-compare?ids={sims[0]}").json()
    assert d["available"] is False


def test_sim_compare_grid_independence(client):
    client.post("/api/v2/seed")
    sims = _ids_by_kind(client, "simulation")
    d = client.get(f"/api/v2/cases/sim-compare?ids={','.join(map(str, sims))}").json()
    assert d["available"] is True
    # 基准 = 网格最细者（case4 12M）
    ref = next(c for c in d["cases"] if c["id"] == d["reference_id"])
    assert ref["mesh_cells"] == max(c["mesh_cells"] for c in d["cases"])
    # 基准算例每行偏差为 0
    for row in d["rows"]:
        refv = next(v for v in row["values"] if v["is_ref"])
        assert refv["deviation_pct"] == 0.0
    # 种子里北航(caseX)壁压偏离大 → 最大偏差 > 3% → LOW
    assert d["max_deviation"] > 3.0
    assert d["verdict_level"] == "LOW"


def test_sim_compare_rejects_experiment(client):
    client.post("/api/v2/seed")
    sims = _ids_by_kind(client, "simulation")
    exps = _ids_by_kind(client, "experiment")
    # 混入一个试验车次也应被过滤，只按仿真算
    d = client.get(f"/api/v2/cases/sim-compare?ids={sims[0]},{sims[1]},{exps[0]}").json()
    assert d["available"] is True
    assert all(c["id"] in sims for c in d["cases"])


# --------------------------------------------------------------------- exp-compare
def test_exp_compare_needs_two(client):
    client.post("/api/v2/seed")
    exps = _ids_by_kind(client, "experiment")
    d = client.get(f"/api/v2/cases/exp-compare?ids={exps[0]}").json()
    assert d["available"] is False


def test_exp_compare_repeatability_and_outlier(client):
    client.post("/api/v2/seed")
    exps = _ids_by_kind(client, "experiment")  # 试车03（真值）
    # 试车09 与 03 几乎一致；试车07 系统性偏高 ~6% → 离群
    id09 = _add_experiment_run("试车09", {
        "wall_p_22": 3.19, "wall_p_24": 3.45, "chamber_p": 2.08, "isolator_ratio": 4.83,
        "thrust": 48.1, "isp": 341, "comb_eff": 0.964, "pt_recovery": 0.418})
    id07 = _add_experiment_run("试车07", {
        "wall_p_22": 3.40, "wall_p_24": 3.68, "chamber_p": 2.23, "isolator_ratio": 5.14,
        "thrust": 50.2, "isp": 345, "comb_eff": 0.962, "pt_recovery": 0.445})
    ids = f"{exps[0]},{id07},{id09}"
    d = client.get(f"/api/v2/cases/exp-compare?ids={ids}").json()
    assert d["available"] is True
    assert len(d["cases"]) == 3
    # 每行有 mean/std/cv
    row = next(r for r in d["rows"] if "燃烧室压力" in r["quantity"])
    assert row["cv_pct"] > 0
    # 07 在多个量上系统性偏离 → 被判为离群
    assert d["outlier_case_id"] == id07
    # 剔除离群后平均 CV 应更小
    assert d["avg_cv_clean"] <= d["avg_cv"]
