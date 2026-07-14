"""评估 Agent API（v2）—— DeepAgents 编排的 SSE 流式接口。

缺 deepagents/langchain 依赖时返回清晰错误，不影响平台其余接口。
"""
from __future__ import annotations

import json

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

router = APIRouter(prefix="/api/v2/agent", tags=["agent"])


class EvaluateReq(BaseModel):
    prompt: str


@router.get("/status")
def status():
    """agent 依赖是否就绪。"""
    try:
        import deepagents  # noqa: F401
        import langchain_openai  # noqa: F401
        return {"ready": True}
    except ImportError as e:
        return {"ready": False, "reason": str(e)}


@router.post("/evaluate")
async def evaluate(req: EvaluateReq):
    """流式跑一次评估编排（SSE）。前端按 data: 行解析。"""
    from app.agents.deep_agent import stream_evaluation

    async def gen():
        try:
            async for chunk in stream_evaluation(req.prompt):
                msgs = chunk.get("messages", []) if isinstance(chunk, dict) else []
                last = msgs[-1] if msgs else None
                content = getattr(last, "content", None) or (last.get("content") if isinstance(last, dict) else "")
                yield f"data: {json.dumps({'content': content}, ensure_ascii=False)}\n\n"
        except Exception as e:  # noqa: BLE001
            yield f"data: {json.dumps({'error': str(e)}, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"})
