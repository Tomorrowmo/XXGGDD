"""
RAGflow 通用模型调用模块
根据 models.json 配置，路由到不同的大模型 API
"""
import json
import os
from typing import AsyncGenerator
from openai import AsyncOpenAI
from dotenv import load_dotenv

load_dotenv()

from app.config import ROOT
MODELS_CONFIG_PATH = ROOT / "models.json"


def load_models() -> list:
    """加载所有模型配置"""
    with open(MODELS_CONFIG_PATH, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data.get("models", [])


def get_model_config(model_id: str) -> dict | None:
    """根据 model_id 获取单个模型配置"""
    models = load_models()
    for m in models:
        if m["id"] == model_id:
            return m
    return None


async def chat_stream(
    model_id: str,
    messages: list,
) -> AsyncGenerator[str, None]:
    """
    通用流式聊天，根据 model_id 路由到对应 API

    messages 格式：[{"role": "user", "content": "..."}, ...]
    """
    cfg = get_model_config(model_id)
    if not cfg:
        yield f"错误：未找到模型配置 {model_id}"
        return

    # 直接 key 优先，否则从环境变量读取
    api_key = cfg.get("api_key", "") or ""
    if not api_key and cfg.get("api_key_env"):
        api_key = os.getenv(cfg["api_key_env"], "")
    if not api_key:
        api_key = "none"
    if not api_key:
        yield f"错误：未配置 API Key（直接 key 或环境变量 {cfg.get('api_key_env', '')}）"
        return

    try:
        client = AsyncOpenAI(api_key=api_key, base_url=cfg["api_base"])

        kwargs = {
            "model": cfg["model_name"],
            "messages": [{"role": m["role"], "content": m["content"]} for m in messages],
            "temperature": cfg.get("temperature", 0.3),
            "max_tokens": cfg.get("max_tokens", 4096),
            "stream": True,
        }

        extra = {k: v for k, v in cfg.get("extra_body", {}).items() if v}
        if extra:
            kwargs["extra_body"] = extra

        if cfg.get("reasoning_effort"):
            kwargs["reasoning_effort"] = cfg["reasoning_effort"]

        stream = await client.chat.completions.create(**kwargs)
        async for chunk in stream:
            delta = chunk.choices[0].delta if chunk.choices else None
            if delta and delta.content:
                yield delta.content

    except Exception as e:
        yield f"API 调用失败：{str(e)}"
