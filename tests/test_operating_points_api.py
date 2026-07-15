"""结构化工况输入相关：canonical_key 生成（含攻角）+ 列表/预览/按参数指派端点。"""
from app.services.operating_point import canonical_key_from_params


def test_key_from_params_variants():
    assert canonical_key_from_params({"Ma": 6.0, "dyn_pressure_kpa": 60}) == "Ma6-60kPa"
    assert canonical_key_from_params({"Ma": 1.2, "aoa": 10.5}) == "Ma1.2-AoA10.5"
    assert canonical_key_from_params({"Ma": 6, "dyn_pressure_kpa": 60, "aoa": 5}) == "Ma6-60kPa-AoA5"
    assert canonical_key_from_params({"dyn_pressure_kpa": 60}) is None  # 缺 Ma
    assert canonical_key_from_params(None) is None


def test_list_operating_points(client):
    client.post("/api/v2/seed")
    d = client.get("/api/v2/operating-points").json()["operating_points"]
    keys = [o["canonical_key"] for o in d]
    assert "Ma6-60kPa" in keys
    assert "__UNALIGNED__" not in keys
    ma6 = next(o for o in d if o["canonical_key"] == "Ma6-60kPa")
    assert ma6["n_cases"] >= 1


def test_preview_key(client):
    d = client.post("/api/v2/operating-points/preview-key",
                    json={"params": {"Ma": 1.2, "aoa": 10.5}}).json()
    assert d["ok"] is True and d["canonical_key"] == "Ma1.2-AoA10.5"
    d2 = client.post("/api/v2/operating-points/preview-key",
                     json={"params": {"dyn_pressure_kpa": 60}}).json()
    assert d2["ok"] is False


def _make_pending(client):
    """入库一个工况无法识别的算例 → PENDING link_id。"""
    from app.db.database import SessionLocal
    from app.db.models import Unit, Delivery, Case, CaseKind, ParseStatus, Confidence
    from app.services.operating_point import align_case
    s = SessionLocal()
    try:
        u = Unit(name="某院", type="承研单位"); s.add(u); s.flush()
        de = Delivery(unit_id=u.id, label="X"); s.add(de); s.flush()
        c = Case(delivery_id=de.id, kind=CaseKind.SIMULATION, name="无名",
                 source_format="openfoam", storage_uri="(t)", content_hash="h1",
                 parse_status=ParseStatus.PARSED, parse_confidence=Confidence.HIGH, context={})
        s.add(c); s.flush()
        lk = align_case(s, c, None)
        s.commit()
        return lk.id, c.id
    finally:
        s.close()


def test_assign_by_params_derives_key(client):
    lid, cid = _make_pending(client)
    r = client.post(f"/api/v2/links/{lid}/assign-op",
                    json={"params": {"Ma": 1.2, "aoa": 10.5}})
    assert r.json()["ok"] is True
    assert r.json()["op"] == "Ma1.2-AoA10.5"
    case = client.get(f"/api/v2/cases/{cid}").json()
    assert case["operating_point"] == "Ma1.2-AoA10.5"


def test_assign_requires_key_or_params(client):
    lid, _ = _make_pending(client)
    r = client.post(f"/api/v2/links/{lid}/assign-op", json={})
    assert r.status_code == 400
