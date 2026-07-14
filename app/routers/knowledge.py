"""知识库 API（v2）—— 知识库注册表 + RAG 问答（诚实标注检索状态）。

真检索需 RAGflow 服务（本地未部署）。故 /query 采取三态：
  - RAGflow 已配（env RAGFLOW_API_URL）→ 走检索（部署接入后返回带出处答案）
  - 否则大模型已配 → LLM 直答兜底，**明确标注无检索、无原文出处，仅供参考**
  - 都没有 → 提示未配置
绝不伪造检索出处。
"""
from __future__ import annotations

import json
import os

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.services.llm import LLMClient

router = APIRouter(prefix="/api/v2/knowledge", tags=["knowledge"])

SSE_HEADERS = {"Cache-Control": "no-cache, no-transform",
               "X-Accel-Buffering": "no", "Connection": "keep-alive"}

# 知识库注册表（可后续落库/落 knowledge.json）
_BASES = [
    {"id": "eval_std", "name": "组合动力评估标准库", "docs": 4, "chunks": 128, "updated": "2026-07-12"},
    {"id": "history", "name": "历史评估报告库", "docs": 17, "chunks": 542, "updated": "2026-07-14"},
    {"id": "literature", "name": "领域文献库", "docs": 33, "chunks": 1204, "updated": "2026-06-30"},
    {"id": "usage_docs", "name": "使用文档", "docs": 6, "chunks": 88, "updated": "2026-07-10"},
]

_KB_SYSTEM = (
    "你是组合动力（火箭/冲压发动机）仿真与试验数据评估领域的专业助手。"
    "当前未接入检索知识库，你的回答基于通用领域知识，**不含本库原文出处**。"
    "请严谨作答：涉及具体规范条款/阈值时，说明这是常见工程经验值而非本库权威条款，"
    "建议用户以本单位评估规范为准。"
)


def _ragflow_ready() -> bool:
    """是否配置了 RAGflow 检索服务（本地默认未配）。"""
    return bool(os.getenv("RAGFLOW_API_URL") and os.getenv("RAGFLOW_API_KEY"))


@router.get("/bases")
def list_bases():
    return {"bases": _BASES}


@router.get("/status")
def kb_status():
    """检索能力自检：给前端诚实展示当前模式。"""
    llm = LLMClient()
    if _ragflow_ready():
        mode = "ragflow"
    elif llm.is_configured:
        mode = "llm_fallback"
    else:
        mode = "unconfigured"
    return {"mode": mode, "retrieval": mode == "ragflow",
            "llm_configured": llm.is_configured, "ragflow_ready": _ragflow_ready()}


class QueryReq(BaseModel):
    base_id: str = "eval_std"
    question: str


@router.post("/query")
async def query(req: QueryReq):
    """非流式 RAG 问答（诚实标注模式）。前端优先用 /query/stream。"""
    if _ragflow_ready():
        # TODO(部署): 接 RAGflow 检索，返回带出处答案
        return {"base_id": req.base_id, "question": req.question,
                "answer": "（RAGflow 已配置，检索接入见部署 TODO）",
                "sources": [], "mode": "ragflow", "retrieval": True}
    llm = LLMClient()
    if not llm.is_configured:
        return {"base_id": req.base_id, "question": req.question, "answer": None,
                "sources": [], "mode": "unconfigured", "retrieval": False,
                "note": "本地未部署 RAGflow 检索服务，且大模型未配置。请在「配置」页填入 API Key，或部署 RAGflow 接入真检索。"}
    try:
        answer = await llm.chat(
            [{"role": "system", "content": _KB_SYSTEM},
             {"role": "user", "content": req.question}], temperature=0.3)
    except Exception as e:  # noqa: BLE001
        return {"base_id": req.base_id, "question": req.question, "answer": None,
                "sources": [], "mode": "error", "retrieval": False, "note": str(e)[:200]}
    return {"base_id": req.base_id, "question": req.question, "answer": answer,
            "sources": [], "mode": "llm_fallback", "retrieval": False,
            "note": "本地无检索库，以上为大模型直答，无原文出处，仅供参考。"}


@router.post("/query/stream")
def query_stream(req: QueryReq):
    """流式 RAG 问答；首个事件 meta 标注模式，随后 delta 流式。"""
    ragflow = _ragflow_ready()
    llm = LLMClient()

    async def gen():
        if ragflow:
            meta = {"mode": "ragflow", "retrieval": True}
            yield f"data: {json.dumps({'meta': meta}, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps({'delta': '（RAGflow 已配置，检索接入见部署 TODO）'}, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"; return
        if not llm.is_configured:
            yield f"data: {json.dumps({'meta': {'mode': 'unconfigured', 'retrieval': False}}, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps({'error': '本地未部署 RAGflow，且大模型未配置。请在「配置」页填 API Key，或部署 RAGflow。'}, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"; return
        yield f"data: {json.dumps({'meta': {'mode': 'llm_fallback', 'retrieval': False, 'note': '本地无检索库，以下为大模型直答，无原文出处，仅供参考。'}}, ensure_ascii=False)}\n\n"
        try:
            async for tok in llm.stream(
                [{"role": "system", "content": _KB_SYSTEM},
                 {"role": "user", "content": req.question}], temperature=0.3):
                yield f"data: {json.dumps({'delta': tok}, ensure_ascii=False)}\n\n"
        except Exception as e:  # noqa: BLE001
            yield f"data: {json.dumps({'error': str(e)[:200]}, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream", headers=SSE_HEADERS)
