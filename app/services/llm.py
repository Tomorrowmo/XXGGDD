"""大模型配置与客户端 —— 配置方式对齐 DataAgent（backend/app/services/llm.py）。

- 默认从 .env 读（LLM_PROVIDER / DEEPSEEK_API_KEY / DEEPSEEK_BASE_URL / DEEPSEEK_MODEL）
- 运行时可在"配置"页 BYOK 覆盖（存 llm_config.json；本项目单租户，故应用级而非 per-user）
- LLMClient(api_key, base_url, model)：优先入参 → BYOK → .env 默认
"""
from __future__ import annotations

import json
from typing import Any, AsyncIterator

import httpx

from app.settings import settings


class LLMError(RuntimeError):
    pass


# --------------------------------------------------------------------------- 配置存储（BYOK）
def load_override() -> dict:
    """读运行时 BYOK 覆盖（llm_config.json）。缺失返回空。"""
    f = settings.llm_config_file
    if f.exists():
        try:
            return json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def save_override(*, api_key: str | None, base_url: str | None, model: str | None) -> dict:
    """保存 BYOK；空串表示清除、回退 .env。"""
    cfg = load_override()
    if api_key is not None:
        ak = api_key.strip()
        cfg["api_key"] = ak or None
    if base_url is not None:
        cfg["base_url"] = base_url.strip() or None
    if model is not None:
        cfg["model"] = model.strip() or None
    settings.llm_config_file.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    return cfg


def effective_config() -> dict:
    """最终生效配置：BYOK 覆盖 → .env 默认。"""
    ov = load_override()
    d = settings.llm
    return {
        "provider": d.provider,
        "api_key": ov.get("api_key") or d.api_key,
        "base_url": ov.get("base_url") or d.base_url,
        "model": ov.get("model") or d.model,
    }


def public_config() -> dict:
    """给前端的脱敏配置（不含 key，只报是否已配）。"""
    c = effective_config()
    return {"provider": c["provider"], "base_url": c["base_url"],
            "model": c["model"], "has_key": bool(c["api_key"])}


# --------------------------------------------------------------------------- 客户端
class LLMClient:
    def __init__(self, api_key: str | None = None, base_url: str | None = None,
                 model: str | None = None):
        c = effective_config()
        self.api_key = api_key or c["api_key"]
        self.base_url = (base_url or c["base_url"]).rstrip("/")
        self.model = model or c["model"]

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key)

    async def chat(self, messages: list[dict], *, temperature: float = 0.2,
                   max_tokens: int = 4000, json_mode: bool = False) -> str:
        if not self.is_configured:
            raise LLMError("大模型未配置。请在 .env 设 DEEPSEEK_API_KEY，或在「配置」页填入 API Key。")
        payload: dict[str, Any] = {"model": self.model, "messages": messages,
                                   "temperature": temperature, "max_tokens": max_tokens, "stream": False}
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        async with httpx.AsyncClient(timeout=120.0) as client:
            r = await client.post(f"{self.base_url}/chat/completions",
                                  headers=self._headers(), json=payload)
            if r.status_code >= 400:
                raise LLMError(f"LLM HTTP {r.status_code}: {r.text[:300]}")
            return r.json()["choices"][0]["message"]["content"]

    async def stream(self, messages: list[dict], *, temperature: float = 0.2,
                     max_tokens: int = 4000) -> AsyncIterator[str]:
        if not self.is_configured:
            raise LLMError("大模型未配置。")
        payload = {"model": self.model, "messages": messages, "temperature": temperature,
                   "max_tokens": max_tokens, "stream": True}
        async with httpx.AsyncClient(timeout=120.0) as client:
            async with client.stream("POST", f"{self.base_url}/chat/completions",
                                     headers=self._headers(), json=payload) as r:
                if r.status_code >= 400:
                    raise LLMError(f"LLM HTTP {r.status_code}")
                async for line in r.aiter_lines():
                    if not line or not line.startswith("data: "):
                        continue
                    data = line[6:]
                    if data == "[DONE]":
                        break
                    try:
                        delta = json.loads(data)["choices"][0]["delta"].get("content")
                        if delta:
                            yield delta
                    except (json.JSONDecodeError, KeyError, IndexError):
                        continue

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}

    async def test(self) -> dict:
        """连通性测试（发一句 ping）。"""
        try:
            reply = await self.chat([{"role": "user", "content": "ping"}], max_tokens=8)
            return {"ok": True, "model": self.model, "reply": reply[:40]}
        except Exception as e:  # noqa: BLE001
            return {"ok": False, "error": str(e)[:200]}
