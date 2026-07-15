"""流式入库进度测试 —— SSE 逐步骤事件 + 末尾 result。"""
import json


def _parse_sse(text: str) -> list[dict]:
    events = []
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("data:"):
            continue
        data = line[5:].strip()
        if not data or data == "[DONE]":
            continue
        events.append(json.loads(data))
    return events


def test_ingest_stream_experiment(client, exp_file):
    r = client.post("/api/v2/ingest/file/stream",
                    json={"path": exp_file, "unit_name": "试车台", "delivery_label": "2026Q1"})
    assert r.status_code == 200
    events = _parse_sse(r.text)
    steps = [e["step"] for e in events if e.get("type") == "progress"]
    # 关键步骤都推了
    for s in ("detect", "dedup", "parse", "align", "write"):
        assert s in steps, f"缺步骤 {s}: {steps}"
    # 末尾 result 成功
    result = [e for e in events if e.get("type") == "result"][-1]
    assert result["ok"] is True
    assert result["n_measurements"] >= 1
    assert result["kind"] == "experiment"


def test_ingest_stream_dedup(client, exp_file):
    # 先入一次
    client.post("/api/v2/ingest/file/stream",
                json={"path": exp_file, "unit_name": "试车台", "delivery_label": "2026Q1"})
    # 再入 → 去重短路
    r = client.post("/api/v2/ingest/file/stream",
                    json={"path": exp_file, "unit_name": "试车台", "delivery_label": "2026Q1"})
    events = _parse_sse(r.text)
    dedup = [e for e in events if e.get("step") == "dedup"]
    assert any("去重" in (e.get("detail") or "") for e in dedup)
    result = [e for e in events if e.get("type") == "result"][-1]
    assert result["deduped"] is True


def test_ingest_stream_bad_path(client):
    r = client.post("/api/v2/ingest/file/stream",
                    json={"path": "D:/nope/missing.txt", "unit_name": "x", "delivery_label": "y"})
    events = _parse_sse(r.text)
    result = [e for e in events if e.get("type") == "result"][-1]
    assert result["ok"] is False
