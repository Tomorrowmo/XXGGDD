"""LangChain 聊天模型工厂 —— 用统一 LLM 配置（对齐 DataAgent，.env + BYOK）。

DeepAgents 需要一个 LangChain BaseChatModel；配置来自 app.services.llm.effective_config()
（DEEPSEEK_API_KEY/BASE_URL/MODEL，或配置页 BYOK 覆盖），OpenAI 兼容。
"""
from __future__ import annotations

from app.services.llm import effective_config


def build_chat_model(*, temperature: float = 0.3):
    """按当前生效 LLM 配置构造 ChatOpenAI。缺依赖时抛清晰错误。"""
    try:
        from langchain_openai import ChatOpenAI
    except ImportError as e:  # noqa: F841
        raise RuntimeError("需安装 langchain-openai：pip install langchain-openai") from e

    c = effective_config()
    return ChatOpenAI(
        model=c["model"],
        base_url=c["base_url"],
        api_key=c["api_key"] or "EMPTY",
        temperature=temperature,
    )
