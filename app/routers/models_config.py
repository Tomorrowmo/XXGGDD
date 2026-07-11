"""模型与 RAG 配置路由：读写 models.json / rag.json、直连测试。"""
import os
import json
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from openai import AsyncOpenAI
from app.config import ROOT

router = APIRouter()


@router.get("/api/models/config")
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


@router.post("/api/models/test")
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


@router.post("/api/models/config")
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


@router.get("/api/rag/config")
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


@router.post("/api/rag/config")
async def save_rag_config(body: dict):
    """保存 rag.json"""
    config_path = ROOT / "rag.json"
    try:
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(body, f, ensure_ascii=False, indent=2)
        return JSONResponse({"ok": True, "message": "RAG 配置已保存"})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)
