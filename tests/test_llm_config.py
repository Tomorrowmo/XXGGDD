"""大模型配置测试（对齐 DataAgent：.env 默认 + BYOK 覆盖 + 脱敏）。"""
import pytest

from app.settings import settings


@pytest.fixture
def iso_llm(monkeypatch, tmp_path):
    """隔离 llm_config.json 到临时路径。"""
    monkeypatch.setattr(settings, "llm_config_file", tmp_path / "llm.json")
    from app.services import llm
    return llm


def test_effective_falls_back_to_env(iso_llm):
    c = iso_llm.effective_config()
    assert c["provider"] == "deepseek"
    assert c["base_url"].startswith("http")
    assert c["model"]


def test_save_override_then_effective(iso_llm):
    iso_llm.save_override(api_key="sk-test-123", base_url="https://x.ai/v1", model="m-1")
    c = iso_llm.effective_config()
    assert c["api_key"] == "sk-test-123"
    assert c["base_url"] == "https://x.ai/v1"
    assert c["model"] == "m-1"


def test_public_config_masks_key(iso_llm):
    iso_llm.save_override(api_key="sk-secret", base_url="", model="")
    pub = iso_llm.public_config()
    assert "api_key" not in pub
    assert pub["has_key"] is True


def test_empty_key_clears(iso_llm):
    iso_llm.save_override(api_key="sk-x", base_url="", model="")
    assert iso_llm.public_config()["has_key"] is True
    iso_llm.save_override(api_key="", base_url="", model="")   # 清除 → 回退 env（空）
    assert iso_llm.public_config()["has_key"] is False


def test_client_is_configured(iso_llm):
    iso_llm.save_override(api_key="sk-x", base_url="", model="")
    assert iso_llm.LLMClient().is_configured is True
    iso_llm.save_override(api_key="", base_url="", model="")
    assert iso_llm.LLMClient().is_configured is False


def test_api_llm_config(client, monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "llm_config_file", tmp_path / "llm.json")
    r = client.get("/api/v2/llm/config")
    d = r.json()
    assert d["provider"] == "deepseek" and "api_key" not in d
    r2 = client.put("/api/v2/llm/config", json={"api_key": "sk-abc", "base_url": "", "model": "deepseek-chat"})
    assert r2.json()["has_key"] is True
