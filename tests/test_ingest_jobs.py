"""后台入库任务：start 返回 job_id，任务在后台线程跑完，轮询能拿到 done 进度。"""
import time


def _wait_done(client, jid, timeout=15.0):
    t0 = time.time()
    j = None
    while time.time() - t0 < timeout:
        j = client.get(f"/api/v2/ingest/jobs/{jid}").json()
        if j.get("status") != "running":
            return j
        time.sleep(0.1)
    return j


def test_background_ingest_single(client, tmp_path):
    f = tmp_path / "t.txt"
    f.write_text("Data info\njunk\nTime (s),ch1,ch2\n0.0,1.0,2.0\n0.1,1.1,2.1\n0.2,1.2,2.3\n",
                 encoding="utf-8")
    r = client.post("/api/v2/ingest/start", json={
        "path": str(f), "unit_name": "U1", "delivery_label": "D1", "batch": False}).json()
    jid = r["job_id"]
    assert jid
    j = _wait_done(client, jid)
    assert j["status"] == "done"
    assert j["total"] == 1 and j["done"] == 1 and j["ok"] == 1
    assert len(j["log"]) == 1 and j["log"][0]["ok"] is True


def test_ingest_jobs_list_and_404(client, tmp_path):
    f = tmp_path / "t2.txt"
    f.write_text("Time (s),a\n0,1\n0.1,2\n", encoding="utf-8")
    jid = client.post("/api/v2/ingest/start", json={
        "path": str(f), "unit_name": "U2", "delivery_label": "D2", "batch": False}).json()["job_id"]
    _wait_done(client, jid)
    jobs = client.get("/api/v2/ingest/jobs").json()["jobs"]
    assert any(x["id"] == jid for x in jobs)
    assert client.get("/api/v2/ingest/jobs/nope").status_code == 404
