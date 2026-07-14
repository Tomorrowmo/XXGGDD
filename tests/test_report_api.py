"""评估报告 HTTP 端点测试（/report/{op} + /export）—— 报告历史列表所依赖。"""


def test_report_ok_after_seed(client):
    client.post("/api/v2/seed")
    d = client.get("/api/v2/report/Ma6-60kPa").json()
    assert d["ok"] is True
    assert "Ma6-60kPa" in d["title"]
    assert d["truth_source"]  # 参照实验车次名
    assert len(d["ranking"]) == 3
    assert d["sections"]["各物理量偏差"]


def test_report_unknown_op(client):
    client.post("/api/v2/seed")
    d = client.get("/api/v2/report/Ma9-99kPa").json()
    assert d["ok"] is False
    assert "reason" in d


def test_report_export_markdown(client):
    client.post("/api/v2/seed")
    r = client.get("/api/v2/report/Ma6-60kPa/export")
    assert r.status_code == 200
    body = r.text
    assert body.startswith("# ")
    assert "## 一、评估范围" in body
    assert "## 四、评级与建议" in body
