"""DeepAgents 装配 —— 主编排 agent + 子 agent（渊/析）。

用户指定架构用 DeepAgents：主 agent 负责规划(todo)/取数/分派/汇总，
子 agent「渊」「析」负责专业物理判断。子 agent 各自只挂需要的工具（最小权限）。
"""
from __future__ import annotations

from functools import lru_cache

from app.settings import settings
from app.agents import prompts, tools
from app.agents.model import build_chat_model


def _build_subagents() -> list[dict]:
    """DeepAgents subagent 定义：name/description/prompt/tools。"""
    yuan = dict(prompts.SUBAGENT_YUAN)
    yuan["tools"] = tools.YUAN_TOOLS
    xi = dict(prompts.SUBAGENT_XI)
    xi["tools"] = tools.XI_TOOLS
    return [yuan, xi]


@lru_cache(maxsize=1)
def get_eval_agent():
    """构造并缓存主评估 agent（懒加载；缺 deepagents 时抛清晰错误）。"""
    try:
        from deepagents import create_deep_agent
    except ImportError as e:  # noqa: F841
        raise RuntimeError(
            "需安装 deepagents：pip install deepagents langgraph langchain-openai"
        ) from e

    model = build_chat_model()
    agent = create_deep_agent(
        tools=tools.ALL_TOOLS,
        system_prompt=prompts.ORCHESTRATOR_PROMPT,
        model=model,
        subagents=_build_subagents(),
    )
    return agent


def run_evaluation(user_prompt: str) -> dict:
    """同步跑一次评估编排。返回 agent 的最终状态。"""
    agent = get_eval_agent()
    return agent.invoke({"messages": [{"role": "user", "content": user_prompt}]})


async def stream_evaluation(user_prompt: str):
    """流式跑评估编排，逐步 yield 事件（供 SSE/WS）。"""
    agent = get_eval_agent()
    async for chunk in agent.astream(
        {"messages": [{"role": "user", "content": user_prompt}]},
        stream_mode="values",
    ):
        yield chunk
