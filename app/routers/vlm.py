"""VLM 视觉分析路由：多轮对话、blow 图分析、CFD 云图分析（均 SSE）。"""
import os
import json
import asyncio
from fastapi import APIRouter
from fastapi.responses import JSONResponse, StreamingResponse
from app.config import ROOT

router = APIRouter()


@router.post("/api/vlm/chat")
async def vlm_chat(body: dict):
    """多轮对话 SSE 流式接口，保持上下文最长 5 轮，支持模型选择"""
    from app.core.vlm_client import chat_stream as vlm_chat_stream
    from app.core.rag_client import get_model_config

    messages = body.get("messages", [])
    model_id = body.get("model_id", "").strip()
    if not messages:
        return JSONResponse({"error": "messages 为空"}, status_code=400)

    if len(messages) > 10:
        messages = messages[-10:]

    image_path = ROOT / "results_png" / "blow-.png"
    if not image_path.exists():
        return JSONResponse({"error": "blow.png 不存在"}, status_code=404)

    # 获取模型配置
    cfg = get_model_config(model_id) if model_id else None
    base_url = cfg["api_base"] if cfg else None
    api_key = cfg.get("api_key", "") or "" if cfg else ""
    if cfg and not api_key and cfg.get("api_key_env"):
        api_key = os.getenv(cfg["api_key_env"], "")
    model_name = cfg["model_name"] if cfg else None

    async def event_stream():
        try:
            async for text in vlm_chat_stream(
                image_path, messages,
                model=model_name, base_url=base_url, api_key=api_key or None,
            ):
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


@router.post("/api/vlm/analyze-blow")
async def vlm_analyze_blow(body: dict):
    """VLM 流式分析 blow.png，支持模型选择"""
    from app.core.vlm_client import analyze_image_stream
    from app.core.rag_client import get_model_config

    model_id = body.get("model_id", "").strip()

    image_path = ROOT / "results_png" / "blow-.png"
    if not image_path.exists():
        return JSONResponse({"error": "blow.png 不存在"}, status_code=404)

    cfg = get_model_config(model_id) if model_id else None
    base_url = cfg["api_base"] if cfg else None
    api_key = cfg.get("api_key", "") or "" if cfg else ""
    if cfg and not api_key and cfg.get("api_key_env"):
        api_key = os.getenv(cfg["api_key_env"], "")
    model_name = cfg["model_name"] if cfg else None

    async def event_stream():
        try:
            async for text in analyze_image_stream(
                image_path, model=model_name,
                base_url=base_url, api_key=api_key or None,
            ):
                yield f"data: {json.dumps({'text': text})}\n\n"
                await asyncio.sleep(0)
            yield f"data: {json.dumps({'done': True})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # 禁用 nginx 缓冲
        },
    )


@router.post("/api/fluent/vlm/analyze")
async def fluent_vlm_analyze(body: dict):
    """VLM 分析 CFD 云图 SSE 流式接口，支持选择模型"""
    from app.core.vlm_client import analyze_cfd_image_stream
    from app.core.rag_client import get_model_config

    image_path = body.get("image_path", "").strip()
    model_id = body.get("model_id", "").strip()
    if not image_path:
        return JSONResponse({"error": "缺少 image_path"}, status_code=400)

    # URL 路径 /case_output/... → 文件系统路径 Case/...
    if image_path.startswith("/case_output/"):
        image_path = "Case" + image_path[len("/case_output"):]
    elif image_path.startswith("/output_plots/"):
        image_path = "output_plots" + image_path[len("/output_plots"):]

    img_p = ROOT / image_path
    if not img_p.is_file():
        return JSONResponse({"error": f"图片不存在: {image_path}"}, status_code=404)

    # 获取模型配置
    cfg = get_model_config(model_id) if model_id else None
    base_url = cfg["api_base"] if cfg else None
    api_key = cfg.get("api_key", "") or "" if cfg else ""
    if cfg and not api_key and cfg.get("api_key_env"):
        api_key = os.getenv(cfg["api_key_env"], "")
    model_name = cfg["model_name"] if cfg else None

    async def event_stream():
        try:
            async for text in analyze_cfd_image_stream(
                str(img_p), model=model_name,
                base_url=base_url, api_key=api_key or None,
            ):
                yield f"data: {json.dumps({'text': text})}\n\n"
                await asyncio.sleep(0)
            yield f"data: {json.dumps({'done': True})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return StreamingResponse(
        event_stream(), media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
