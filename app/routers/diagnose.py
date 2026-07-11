"""LLM 诊断路由：SSE 流式数据诊断。"""
import json
import asyncio
from fastapi import APIRouter
from fastapi.responses import JSONResponse, StreamingResponse

router = APIRouter()


@router.post("/api/llm/diagnose")
async def llm_diagnose(body: dict):
    """LLM 数据诊断 SSE 流式接口，支持模型选择"""
    from app.core.plotter import compute_channel_stats
    from app.core.llm_client import SYSTEM_PROMPT, _build_validation_summary
    from app.core.rag_client import chat_stream

    filename = body.get("filename", "")
    model_id = body.get("model_id", "").strip()
    if not filename:
        return JSONResponse({"error": "缺少 filename 参数"}, status_code=400)

    chat_history = body.get("messages", None)

    try:
        stats_result = compute_channel_stats(filename)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

    # 构建诊断消息
    summary = _build_validation_summary(stats_result["stats"])
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    if chat_history and len(chat_history) > 0:
        messages.append({"role": "user", "content": f"以下是本次试验的数据摘要：\n\n{summary}"})
        recent = chat_history[-10:] if len(chat_history) > 10 else chat_history
        messages.extend(recent)
    else:
        messages.append({"role": "user", "content": summary})

    async def event_stream():
        try:
            async for text in chat_stream(model_id, messages):
                yield f"data: {json.dumps({'text': text})}\n\n"
                await asyncio.sleep(0)
            yield f"data: {json.dumps({'done': True})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return StreamingResponse(
        event_stream(), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
