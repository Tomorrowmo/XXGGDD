"""RAGflow 通用对话路由：模型列表、通用聊天（SSE）、连接测试。"""
import os
import json
import asyncio
from fastapi import APIRouter
from fastapi.responses import JSONResponse, StreamingResponse
from openai import AsyncOpenAI

router = APIRouter()


@router.get("/api/ragflow/models")
async def ragflow_models():
    """获取所有可用模型列表"""
    from app.core.rag_client import load_models

    models = load_models()
    # 只返回前端需要的字段，隐藏敏感配置
    return JSONResponse([{
        "id": m["id"],
        "name": m["name"],
        "provider": m["provider"],
        "multimodal": m.get("multimodal", False),
        "max_tokens": m.get("max_tokens", 4096),
    } for m in models])


@router.post("/api/ragflow/chat")
async def ragflow_chat(body: dict):
    """RAGflow 通用聊天 SSE 流式接口"""
    from app.core.rag_client import chat_stream

    model_id = body.get("model_id", "")
    messages = body.get("messages", [])

    if not model_id:
        return JSONResponse({"error": "缺少 model_id 参数"}, status_code=400)
    if not messages:
        return JSONResponse({"error": "messages 为空"}, status_code=400)

    # 只保留最近 10 条消息
    if len(messages) > 10:
        messages = messages[-10:]

    async def event_stream():
        try:
            async for text in chat_stream(model_id, messages):
                yield f"data: {json.dumps({'text': text})}\n\n"
                await asyncio.sleep(0)
            yield f"data: {json.dumps({'done': True})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/api/ragflow/test")
async def ragflow_test(body: dict):
    """测试模型连接：发一条极短请求验证 API 可达性"""
    import time
    from app.core.rag_client import get_model_config

    model_id = body.get("model_id", "")
    if not model_id:
        return JSONResponse({"ok": False, "message": "缺少 model_id"}, status_code=400)

    cfg = get_model_config(model_id)
    if not cfg:
        return JSONResponse({"ok": False, "message": f"未找到模型 {model_id}"}, status_code=404)

    api_key = os.getenv(cfg["api_key_env"], "") if cfg.get("api_key_env") else "none"
    if not api_key:
        return JSONResponse({"ok": False, "message": f"未配置 {cfg['api_key_env']}"})

    try:
        client = AsyncOpenAI(api_key=api_key, base_url=cfg["api_base"])
        t0 = time.time()
        resp = await client.chat.completions.create(
            model=cfg["model_name"],
            messages=[{"role": "user", "content": "ping"}],
            max_tokens=1,
            temperature=0,
            stream=False,
        )
        elapsed = round((time.time() - t0) * 1000)
        return JSONResponse({"ok": True, "message": f"连接正常 ({elapsed}ms)"})
    except Exception as e:
        return JSONResponse({"ok": False, "message": str(e)[:120]})
