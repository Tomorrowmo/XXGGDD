"""
航天发动机热试车数据分析 Web Demo
FastAPI 后端 + 静态前端页面

运行方式：
    source /opt/miniconda3/etc/profile.d/conda.sh && conda activate gy_pytorch
    python demo_server.py

    浏览器访问：http://localhost:8501
    接口文档：http://localhost:8501/docs
"""
import json
import os
import asyncio
import uvicorn
from pathlib import Path
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from openai import AsyncOpenAI

from app.config import ROOT, DATA_DIR
from app.routers import files as files_router
from app.routers import charts as charts_router
from app.routers import diagnose as diagnose_router
from app.routers import vlm as vlm_router

app = FastAPI(title="组合动力智能评估", version="0.1.0")

# 静态文件：前端页面、图片
app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")
app.mount("/results_png", StaticFiles(directory=ROOT / "results_png"), name="results_png")

# Fluent 仿真：Case 目录图片访问 + 后处理 API
case_dir = (ROOT / "Case").resolve()
output_dir = (ROOT / "output_plots").resolve()
output_dir.mkdir(parents=True, exist_ok=True)
if case_dir.is_dir():
    app.mount("/case_output", StaticFiles(directory=str(case_dir)), name="case_output")
app.mount("/output_plots", StaticFiles(directory=str(output_dir)), name="output_plots")

from app.core.qjz_fluent_post.http_api import create_fluent_router
fluent_router = create_fluent_router(ROOT)
app.include_router(fluent_router)
app.include_router(files_router.router)
app.include_router(charts_router.router)
app.include_router(diagnose_router.router)
app.include_router(vlm_router.router)


@app.get("/")
async def index():
    """主页面"""
    return FileResponse(ROOT / "static" / "index.html")


@app.get("/help")
async def docs_page():
    """使用文档页面"""
    return FileResponse(ROOT / "static" / "docs.html")


# ---------------------------------------------------------------------------
# API：RAGflow 通用模型对话
# ---------------------------------------------------------------------------
@app.get("/api/ragflow/models")
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


@app.post("/api/ragflow/chat")
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


# ---------------------------------------------------------------------------
# API：模型配置管理（读写 models.json）
# ---------------------------------------------------------------------------
@app.get("/api/models/config")
async def get_models_config():
    """读取 models.json，api_key 字段脱敏返回"""
    config_path = ROOT / "models.json"
    if not config_path.is_file():
        return JSONResponse({"error": "models.json 不存在"}, status_code=404)
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        # 脱敏：api_key 替换为占位符
        for m in data.get("models", []):
            if m.get("api_key"):
                m["api_key"] = "****"
        return JSONResponse(data)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.post("/api/models/test")
async def test_model_direct(body: dict):
    """直接用传入的模型配置测试连接（无需先保存到 models.json）"""
    import time
    cfg = body.get("model", {})
    if not cfg:
        return JSONResponse({"ok": False, "message": "缺少 model 配置"}, status_code=400)

    # 直接 key 优先，否则从环境变量读取
    api_key = cfg.get("api_key", "") or ""
    if not api_key and cfg.get("api_key_env"):
        api_key = os.getenv(cfg["api_key_env"], "")
    if not api_key:
        api_key = "none"
    if not api_key:
        return JSONResponse({"ok": False, "message": "未配置 API Key"})

    try:
        client = AsyncOpenAI(api_key=api_key, base_url=cfg.get("api_base", ""))
        t0 = time.time()
        await client.chat.completions.create(
            model=cfg.get("model_name", ""),
            messages=[{"role": "user", "content": "ping"}],
            max_tokens=1, temperature=0, stream=False,
        )
        elapsed = round((time.time() - t0) * 1000)
        return JSONResponse({"ok": True, "message": f"连接正常 ({elapsed}ms)"})
    except Exception as e:
        return JSONResponse({"ok": False, "message": str(e)[:120]})


@app.post("/api/models/config")
async def save_models_config(body: dict):
    """保存 models.json，api_key 为 **** 时保留原值"""
    config_path = ROOT / "models.json"
    try:
        # 读取旧配置，保留被脱敏的 api_key
        old_models = {}
        if config_path.is_file():
            with open(config_path, "r", encoding="utf-8") as f:
                old = json.load(f)
            for m in old.get("models", []):
                if m.get("api_key"):
                    old_models[m["id"]] = m["api_key"]

        new_models = body.get("models", [])
        for m in new_models:
            if m.get("api_key") == "****" and m["id"] in old_models:
                m["api_key"] = old_models[m["id"]]
            elif m.get("api_key") == "":
                m.pop("api_key", None)

        with open(config_path, "w", encoding="utf-8") as f:
            json.dump({"models": new_models}, f, ensure_ascii=False, indent=2)
        return JSONResponse({"ok": True, "message": "配置已保存"})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


# ---------------------------------------------------------------------------
# API：RAG 知识库配置（读写 rag.json）
# ---------------------------------------------------------------------------
@app.get("/api/rag/config")
async def get_rag_config():
    """读取 rag.json"""
    config_path = ROOT / "rag.json"
    if not config_path.is_file():
        return JSONResponse({"iframe_url": ""})
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return JSONResponse(data)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.post("/api/rag/config")
async def save_rag_config(body: dict):
    """保存 rag.json"""
    config_path = ROOT / "rag.json"
    try:
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(body, f, ensure_ascii=False, indent=2)
        return JSONResponse({"ok": True, "message": "RAG 配置已保存"})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.post("/api/ragflow/test")
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


if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8501, reload=True)
