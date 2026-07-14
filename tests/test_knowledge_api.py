"""知识库检索端点测试 —— 诚实三态（ragflow / llm_fallback / unconfigured），不伪造出处。"""
from app.settings import settings


def test_status_unconfigured(client, monkeypatch, tmp_path):
    # 无 RAGflow、无 LLM key → unconfigured
    monkeypatch.delenv("RAGFLOW_API_URL", raising=False)
    monkeypatch.setattr(settings, "llm_config_file", tmp_path / "llm.json")
    monkeypatch.setattr(settings.llm, "api_key", "")
    d = client.get("/api/v2/knowledge/status").json()
    assert d["mode"] == "unconfigured"
    assert d["retrieval"] is False


def test_query_unconfigured_no_fake_sources(client, monkeypatch, tmp_path):
    monkeypatch.delenv("RAGFLOW_API_URL", raising=False)
    monkeypatch.setattr(settings, "llm_config_file", tmp_path / "llm.json")
    monkeypatch.setattr(settings.llm, "api_key", "")
    d = client.post("/api/v2/knowledge/query", json={"question": "偏差多少算合格"}).json()
    assert d["mode"] == "unconfigured"
    assert d["sources"] == []        # 绝不伪造出处
    assert d["answer"] is None
    assert "note" in d


def test_status_llm_fallback(client, monkeypatch, tmp_path):
    # 有 LLM key、无 RAGflow → llm_fallback
    monkeypatch.delenv("RAGFLOW_API_URL", raising=False)
    monkeypatch.setattr(settings, "llm_config_file", tmp_path / "llm.json")
    monkeypatch.setattr(settings.llm, "api_key", "sk-test-not-real")
    d = client.get("/api/v2/knowledge/status").json()
    assert d["mode"] == "llm_fallback"
    assert d["retrieval"] is False
    assert d["llm_configured"] is True


def test_query_stream_unconfigured(client, monkeypatch, tmp_path):
    monkeypatch.delenv("RAGFLOW_API_URL", raising=False)
    monkeypatch.setattr(settings, "llm_config_file", tmp_path / "llm.json")
    monkeypatch.setattr(settings.llm, "api_key", "")
    r = client.post("/api/v2/knowledge/query/stream", json={"question": "x"})
    assert r.status_code == 200
    body = r.text
    assert "unconfigured" in body
    assert "[DONE]" in body


def test_bases_list(client):
    d = client.get("/api/v2/knowledge/bases").json()
    assert len(d["bases"]) >= 1
