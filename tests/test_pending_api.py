"""PENDING 人工对齐 HTTP 流程测试（/pending + /links/{id}/assign-op）。

覆盖：工况未识别的算例落 PENDING → 列出 → 人工指定工况 → PENDING 清空、
算例并入该工况（可进对比）。
"""
from sqlalchemy import select

from app.db.database import SessionLocal
from app.db.models import (
    Unit, Delivery, Case, CaseKind, ParseStatus, Confidence,
)
from app.services.operating_point import align_case


def _make_unaligned_case(name: str = "无名算例") -> int:
    """建一个工况无法自动识别的仿真算例（落 PENDING 链接）。"""
    s = SessionLocal()
    try:
        u = Unit(name="某院", type="承研单位"); s.add(u); s.flush()
        d = Delivery(unit_id=u.id, label="交付X"); s.add(d); s.flush()
        c = Case(delivery_id=d.id, kind=CaseKind.SIMULATION, name=name,
                 source_format="openfoam", storage_uri="(test)",
                 content_hash=f"test-{name}", parse_status=ParseStatus.PARSED,
                 parse_confidence=Confidence.HIGH, context={})
        s.add(c); s.flush()
        link = align_case(s, c, params=None)   # 无参数 + 名字无工况 → PENDING
        assert link.mapping_confidence == Confidence.PENDING
        s.commit()
        return c.id
    finally:
        s.close()


def test_pending_list_then_assign(client):
    cid = _make_unaligned_case()
    # 列出待对齐
    pend = client.get("/api/v2/pending").json()["pending"]
    assert any(p["case_id"] == cid for p in pend)
    item = next(p for p in pend if p["case_id"] == cid)
    assert item["unit"] == "某院"

    # 指定工况
    r = client.post(f"/api/v2/links/{item['link_id']}/assign-op",
                    json={"canonical_key": "Ma6-60kPa",
                          "params": {"Ma": 6.0, "dyn_pressure_kpa": 60}})
    assert r.json()["ok"] is True

    # PENDING 清空
    pend2 = client.get("/api/v2/pending").json()["pending"]
    assert all(p["case_id"] != cid for p in pend2)

    # 算例已并入该工况
    case = client.get(f"/api/v2/cases/{cid}").json()
    assert case["operating_point"] == "Ma6-60kPa"
    assert case["mapping_confidence"] == "HIGH"


def test_assign_bad_link(client):
    r = client.post("/api/v2/links/99999/assign-op", json={"canonical_key": "Ma6-60kPa"})
    assert r.status_code == 404
