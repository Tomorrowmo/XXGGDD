"""删除算例：移除库内记录（级联测量/工况对齐），不动原始文件。"""


def test_delete_case_removes_record_and_cascades(client):
    client.post("/api/v2/seed")
    cases = client.get("/api/v2/cases").json()["cases"]
    n0 = len(cases)
    target = cases[0]
    cid = target["id"]

    # 删前该算例有测量（种子仿真/试验都写了测量）
    from app.db.database import SessionLocal
    from app.db.models import Measurement, Case
    s = SessionLocal()
    n_meas = s.query(Measurement).filter(Measurement.case_id == cid).count()
    s.close()

    r = client.delete(f"/api/v2/cases/{cid}").json()
    assert r["ok"] is True and r["deleted"] == target["name"]

    cases2 = client.get("/api/v2/cases").json()["cases"]
    assert len(cases2) == n0 - 1
    assert all(c["id"] != cid for c in cases2)

    # 级联：测量随之删除
    s = SessionLocal()
    assert s.query(Measurement).filter(Measurement.case_id == cid).count() == 0
    assert s.get(Case, cid) is None
    s.close()

    # 再删同一个 → 404
    assert client.delete(f"/api/v2/cases/{cid}").status_code == 404


def test_delete_case_404_for_missing(client):
    assert client.delete("/api/v2/cases/999999").status_code == 404
