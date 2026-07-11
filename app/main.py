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
import shutil
import asyncio
import uvicorn
from pathlib import Path
from fastapi import FastAPI, UploadFile, File
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from openai import AsyncOpenAI

from app.config import ROOT, DATA_DIR

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


@app.get("/")
async def index():
    """主页面"""
    return FileResponse(ROOT / "static" / "index.html")


@app.get("/help")
async def docs_page():
    """使用文档页面"""
    return FileResponse(ROOT / "static" / "docs.html")


# ---------------------------------------------------------------------------
# API：数据信息
# ---------------------------------------------------------------------------
@app.get("/api/data/info")
async def data_info(filename: str):
    """读取 data/ 目录下指定文件的 header 信息和基本统计"""
    from A00_parameterData import headerIndex

    file_path = ROOT / "data" / filename
    if not file_path.exists():
        return JSONResponse({"error": f"文件 {filename} 不存在"}, status_code=404)

    try:
        # 读取原始行
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()

        total_lines = len(lines)
        if total_lines <= headerIndex:
            return JSONResponse({"error": "文件行数不足，headerIndex 超出范围"}, status_code=400)

        # 解析 header
        header_line = lines[headerIndex].strip()
        headers = [h.strip() for h in header_line.split(",")]

        # 统计数据行
        data_rows = total_lines - headerIndex - 1

        # 采样前几行数据
        sample_rows = []
        for i in range(headerIndex + 1, min(headerIndex + 4, total_lines)):
            sample_rows.append(lines[i].strip())

        return JSONResponse({
            "filename": filename,
            "total_lines": total_lines,
            "header_index": headerIndex,
            "column_count": len(headers),
            "data_rows": data_rows,
            "headers": headers,
            "sample_rows": sample_rows,
            "size_bytes": file_path.stat().st_size,
        })
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


# ---------------------------------------------------------------------------
# API：交互图表数据
# ---------------------------------------------------------------------------
@app.post("/api/chart/pressure-curve")
async def chart_pressure_curve(body: dict):
    """根据用户选择的数据文件 + 列索引，生成压力-时间曲线 Plotly JSON"""
    from app.core.plotter import build_pressure_curve

    filename = body.get("filename", "")
    time_col = body.get("time_col", 0)
    value_cols = body.get("value_cols", [])

    if not filename:
        return JSONResponse({"error": "缺少 filename 参数"}, status_code=400)
    if not value_cols:
        return JSONResponse({"error": "缺少 value_cols 参数"}, status_code=400)

    try:
        fig = build_pressure_curve(filename, time_col, value_cols)
        return JSONResponse(content=json.loads(fig.to_json()))
    except FileNotFoundError as e:
        return JSONResponse({"error": str(e)}, status_code=404)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.post("/api/llm/diagnose")
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


@app.post("/api/stats/compute")
async def stats_compute(body: dict):
    """计算所有流道通道的统计值"""
    from app.core.plotter import compute_channel_stats

    filename = body.get("filename", "")
    if not filename:
        return JSONResponse({"error": "缺少 filename 参数"}, status_code=400)

    try:
        result = compute_channel_stats(filename)
        return JSONResponse(result)
    except FileNotFoundError as e:
        return JSONResponse({"error": str(e)}, status_code=404)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/api/chart/channels")
async def chart_channels(filename: str):
    """获取文件中所有「流道」相关列的索引和标签"""
    from app.core.plotter import _read_file, extract_channels

    filepath = DATA_DIR / filename
    if not filepath.exists():
        return JSONResponse({"error": f"文件 {filename} 不存在"}, status_code=404)

    try:
        headers, _ = _read_file(filepath)
        channels = extract_channels(headers)
        time_cols = [i for i, h in enumerate(headers) if "time" in h.lower() or "Time" in h]
        return JSONResponse({
            "channels": channels,
            "time_cols": time_cols,
            "total_cols": len(headers),
        })
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.post("/api/upload")
async def upload_file(file: UploadFile = File(...)):
    """上传试验数据文件到 data/ 目录"""
    if not file.filename:
        return JSONResponse({"error": "文件名为空"}, status_code=400)

    data_dir = ROOT / "data"
    data_dir.mkdir(exist_ok=True)

    save_path = data_dir / file.filename
    with open(save_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    file_size = save_path.stat().st_size
    return JSONResponse({
        "filename": file.filename,
        "size_bytes": file_size,
        "message": f"文件 {file.filename} 上传成功",
    })


@app.get("/api/files")
async def list_files():
    """列出 data/ 目录下已上传的文件"""
    data_dir = ROOT / "data"
    if not data_dir.exists():
        return JSONResponse({"files": []})
    files = sorted(data_dir.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True)
    return JSONResponse({
        "files": [{"name": f.name, "size_bytes": f.stat().st_size} for f in files if f.is_file()]
    })


@app.delete("/api/files/{filename}")
async def delete_file(filename: str):
    """删除 data/ 目录下的文件"""
    file_path = ROOT / "data" / filename
    if not file_path.exists():
        return JSONResponse({"error": "文件不存在"}, status_code=404)
    try:
        file_path.unlink()
        return JSONResponse({"message": f"文件 {filename} 已删除"})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.put("/api/files/{filename}/rename")
async def rename_file(filename: str, body: dict):
    """重命名 data/ 目录下的文件"""
    new_name = body.get("new_name", "").strip()
    if not new_name:
        return JSONResponse({"error": "新文件名不能为空"}, status_code=400)
    old_path = ROOT / "data" / filename
    new_path = ROOT / "data" / new_name
    if not old_path.exists():
        return JSONResponse({"error": "文件不存在"}, status_code=404)
    if new_path.exists():
        return JSONResponse({"error": "目标文件名已存在"}, status_code=409)
    try:
        old_path.rename(new_path)
        return JSONResponse({"message": f"{filename} → {new_name} 重命名成功"})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


# ---------------------------------------------------------------------------
# API：VLM 多轮对话
# ---------------------------------------------------------------------------
@app.post("/api/vlm/chat")
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


# ---------------------------------------------------------------------------
# API：VLM 流式分析
# ---------------------------------------------------------------------------
@app.post("/api/vlm/analyze-blow")
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


@app.post("/api/fluent/vlm/analyze")
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
