"""通用对话 API（v2）—— 对齐 DataAgent：持久化会话 + 消息历史 + 流式对话。"""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db, SessionLocal
from app.db.models import Conversation, Message
from app.services.llm import LLMClient

router = APIRouter(prefix="/api/v2/chat", tags=["chat"])

SYSTEM_PROMPT = ("你是「组合动力智能评估平台」的助手，擅长火箭/组合动力发动机的"
                 "仿真与实验数据评估、收敛/QOI 判据、多源对比。回答简洁专业，用中文。")

# 让 SSE 逐 token 流出（对齐 DataAgent 的头）
SSE_HEADERS = {"Cache-Control": "no-cache, no-transform",
               "X-Accel-Buffering": "no", "Connection": "keep-alive"}


# ------------------------------------------------------------------ 会话 CRUD
class ConvResp(BaseModel):
    id: int
    title: str
    n_messages: int = 0


class CreateConvReq(BaseModel):
    title: str = "新对话"


class RenameReq(BaseModel):
    title: str


@router.post("/conversations", response_model=ConvResp)
def create_conv(body: CreateConvReq, db: Session = Depends(get_db)):
    c = Conversation(title=body.title or "新对话")
    db.add(c); db.commit(); db.refresh(c)
    return ConvResp(id=c.id, title=c.title, n_messages=0)


@router.get("/conversations", response_model=list[ConvResp])
def list_convs(db: Session = Depends(get_db)):
    rows = db.execute(select(Conversation).order_by(Conversation.id.desc())).scalars().all()
    return [ConvResp(id=c.id, title=c.title, n_messages=len(c.messages)) for c in rows]


@router.patch("/conversations/{conv_id}", response_model=ConvResp)
def rename_conv(conv_id: int, body: RenameReq, db: Session = Depends(get_db)):
    c = db.get(Conversation, conv_id)
    if c is None:
        raise HTTPException(404, "会话不存在")
    c.title = (body.title or "").strip()[:200] or c.title
    db.commit()
    return ConvResp(id=c.id, title=c.title, n_messages=len(c.messages))


@router.delete("/conversations/{conv_id}")
def delete_conv(conv_id: int, db: Session = Depends(get_db)):
    c = db.get(Conversation, conv_id)
    if c is None:
        raise HTTPException(404, "会话不存在")
    db.delete(c); db.commit()
    return {"ok": True}


class MsgResp(BaseModel):
    id: int
    role: str
    content: str


@router.get("/conversations/{conv_id}/messages", response_model=list[MsgResp])
def get_messages(conv_id: int, db: Session = Depends(get_db)):
    c = db.get(Conversation, conv_id)
    if c is None:
        raise HTTPException(404, "会话不存在")
    return [MsgResp(id=m.id, role=m.role, content=m.content) for m in c.messages]


# ------------------------------------------------------------------ 流式对话
class SendReq(BaseModel):
    content: str
    temperature: float = 0.3


@router.post("/conversations/{conv_id}/stream")
def send_stream(conv_id: int, req: SendReq, db: Session = Depends(get_db)):
    """存用户消息 → 带历史调 LLM 流式 → 存 assistant 消息。"""
    conv = db.get(Conversation, conv_id)
    if conv is None:
        raise HTTPException(404, "会话不存在")

    # 存用户消息；首条消息自动命名会话
    db.add(Message(conversation_id=conv_id, role="user", content=req.content))
    if conv.title == "新对话":
        conv.title = req.content.strip()[:30]
    db.commit()

    # 组装历史（含刚存的用户消息）
    history = [{"role": m.role, "content": m.content} for m in conv.messages]
    msgs = [{"role": "system", "content": SYSTEM_PROMPT}] + history
    client = LLMClient()

    async def gen():
        acc = ""
        if not client.is_configured:
            yield f"data: {json.dumps({'error': '大模型未配置，请在「配置」页填入 API Key'}, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"
            return
        try:
            async for tok in client.stream(msgs, temperature=req.temperature):
                acc += tok
                yield f"data: {json.dumps({'delta': tok}, ensure_ascii=False)}\n\n"
        except Exception as e:  # noqa: BLE001
            yield f"data: {json.dumps({'error': str(e)[:200]}, ensure_ascii=False)}\n\n"
        # 用新会话存 assistant（生成器在请求会话关闭后运行）
        if acc:
            s = SessionLocal()
            try:
                s.add(Message(conversation_id=conv_id, role="assistant", content=acc))
                s.commit()
            finally:
                s.close()
        yield "data: [DONE]\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream", headers=SSE_HEADERS)


@router.post("/stream")
def stateless_stream(req: dict, db: Session = Depends(get_db)):
    """无会话的简单流式（兼容旧调用）。body: {messages, temperature}。"""
    messages = req.get("messages") or []
    client = LLMClient()

    async def gen():
        if not client.is_configured:
            yield f"data: {json.dumps({'error': '大模型未配置'}, ensure_ascii=False)}\n\n"
            yield "data: [DONE]\n\n"; return
        try:
            async for tok in client.stream(messages, temperature=req.get("temperature", 0.3)):
                yield f"data: {json.dumps({'delta': tok}, ensure_ascii=False)}\n\n"
        except Exception as e:  # noqa: BLE001
            yield f"data: {json.dumps({'error': str(e)[:200]}, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream", headers=SSE_HEADERS)
