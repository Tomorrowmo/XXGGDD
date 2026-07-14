"""API 集成测试（FastAPI TestClient）—— v2 全套端点。"""
from app.settings import settings


def test_chat_stream_no_key(client, monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "llm_config_file", tmp_path / "llm.json")
    monkeypatch.setattr(settings.llm, "api_key", "")
    r = client.post("/api/v2/chat/stream", json={"messages": [{"role": "user", "content": "hi"}]})
    assert r.status_code == 200
    assert "未配置" in r.text or "error" in r.text


def test_conversation_crud(client):
    # 建会话
    c = client.post("/api/v2/chat/conversations", json={"title": "测试会话"}).json()
    cid = c["id"]
    assert c["title"] == "测试会话"
    # 列会话
    convs = client.get("/api/v2/chat/conversations").json()
    assert any(x["id"] == cid for x in convs)
    # 改名
    r = client.patch(f"/api/v2/chat/conversations/{cid}", json={"title": "改名了"})
    assert r.json()["title"] == "改名了"
    # 消息为空
    assert client.get(f"/api/v2/chat/conversations/{cid}/messages").json() == []
    # 删除
    assert client.delete(f"/api/v2/chat/conversations/{cid}").json()["ok"] is True
    assert client.get(f"/api/v2/chat/conversations/{cid}/messages").status_code == 404


def test_conversation_stream_saves_user_msg(client, monkeypatch, tmp_path):
    # 无 key：流式返回错误，但用户消息应已存库
    monkeypatch.setattr(settings, "llm_config_file", tmp_path / "llm.json")
    monkeypatch.setattr(settings.llm, "api_key", "")
    cid = client.post("/api/v2/chat/conversations", json={}).json()["id"]
    r = client.post(f"/api/v2/chat/conversations/{cid}/stream", json={"content": "壁压偏差多少算合格"})
    assert r.status_code == 200
    msgs = client.get(f"/api/v2/chat/conversations/{cid}/messages").json()
    assert any(m["role"] == "user" and "壁压" in m["content"] for m in msgs)
    # 首条消息自动命名会话
    conv = [c for c in client.get("/api/v2/chat/conversations").json() if c["id"] == cid][0]
    assert conv["title"].startswith("壁压")


def test_seed_and_cases(client):
    r = client.post("/api/v2/seed")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] and body["cases"] == 4

    r = client.get("/api/v2/cases")
    cases = r.json()["cases"]
    assert len(cases) == 4
    names = {c["name"] for c in cases}
    assert {"case4", "caseZ", "caseX", "试车03"} <= names
    # 全部对齐到同一工况
    assert all(c["operating_point"] == "Ma6-60kPa" for c in cases)


def test_units_endpoint(client):
    client.post("/api/v2/seed")
    r = client.get("/api/v2/units")
    units = {u["name"] for u in r.json()["units"]}
    assert {"西工大", "航天六院", "北航", "试车台"} <= units


def test_compare_endpoint(client):
    client.post("/api/v2/seed")
    r = client.get("/api/v2/compare/operating-point/Ma6-60kPa")
    d = r.json()
    assert d["ranking"][0]["unit"] == "西工大"
    assert len(d["rows"]) == 8


def test_compare_unknown_op(client):
    r = client.get("/api/v2/compare/operating-point/NoSuch")
    assert r.status_code == 200
    assert r.json()["ranking"] == []


def test_report_endpoint(client):
    client.post("/api/v2/seed")
    r = client.get("/api/v2/report/Ma6-60kPa?engine=XF-2")
    d = r.json()
    assert d["ok"]
    assert "XF-2" in d["title"]


def test_case_detail_and_filter(client):
    client.post("/api/v2/seed")
    cases = client.get("/api/v2/cases?unit=北航").json()["cases"]
    assert len(cases) == 1 and cases[0]["name"] == "caseX"
    cid = cases[0]["id"]
    detail = client.get(f"/api/v2/cases/{cid}").json()
    assert detail["name"] == "caseX"
    assert len(detail["measurements"]) == 8


def test_knowledge_bases(client):
    r = client.get("/api/v2/knowledge/bases")
    names = [b["name"] for b in r.json()["bases"]]
    assert "组合动力评估标准库" in names


def test_agent_status(client):
    r = client.get("/api/v2/agent/status")
    assert "ready" in r.json()


def test_search_endpoint(client):
    client.post("/api/v2/seed")
    r = client.get("/api/v2/search", params={"q": "北航的仿真算例"})
    d = r.json()
    assert d["answer_type"] == "cases"
    assert all(c["unit"] == "北航" for c in d["results"])


def test_search_ranking(client):
    client.post("/api/v2/seed")
    r = client.get("/api/v2/search", params={"q": "哪家偏差最小"})
    d = r.json()
    assert d["answer_type"] == "ranking"
    assert d["answer"][0]["unit"] == "西工大"


def test_report_export(client):
    client.post("/api/v2/seed")
    r = client.get("/api/v2/report/Ma6-60kPa/export")
    assert r.status_code == 200
    assert r.text.startswith("#")
    assert "评级与建议" in r.text


def test_experiment_analysis(client, exp_file):
    r = client.post("/api/v2/ingest/file",
                    json={"path": exp_file, "unit_name": "试车台", "delivery_label": "Q1"})
    cid = r.json()["case_id"]
    d = client.get(f"/api/v2/cases/{cid}/experiment").json()
    assert d["available"]
    assert d["n_channels"] >= 3
    assert d["curves"] and d["steady_qoi"]
    assert "steady" in d["phases"]


def test_experiment_analysis_seed_no_file(client):
    client.post("/api/v2/seed")
    # 种子试车03 无真实文件 → available False
    cases = client.get("/api/v2/cases?kind=experiment").json()["cases"]
    cid = cases[0]["id"]
    d = client.get(f"/api/v2/cases/{cid}/experiment").json()
    assert d["available"] is False


def test_platform_page(client):
    r = client.get("/platform")
    assert r.status_code == 200
    assert "组合动力智能评估" in r.text
