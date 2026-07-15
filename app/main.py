"""
航天发动机热试车数据分析 Web Demo
FastAPI 后端 + 静态前端页面

运行方式：
    source /opt/miniconda3/etc/profile.d/conda.sh && conda activate gy_pytorch
    python demo_server.py

    浏览器访问：http://localhost:8501
    接口文档：http://localhost:8501/docs
"""
import uvicorn
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from app.config import ROOT
from app.routers import files as files_router
from app.routers import charts as charts_router
from app.routers import diagnose as diagnose_router
from app.routers import vlm as vlm_router
from app.routers import ragflow as ragflow_router
from app.routers import models_config as models_config_router
# 重构新增（评估平台 v2）
from app.routers import library as library_router
from app.routers import compare as compare_router
from app.routers import agent as agent_router
from app.routers import report as report_router
from app.routers import knowledge as knowledge_router
from app.routers import search as search_router
from app.routers import llm_config as llm_config_router
from app.routers import chat_v2 as chat_v2_router
from app.routers import analysis as analysis_router
from app.routers import config as config_router
from app.routers import fs as fs_router
from app.routers import formulas as formulas_router
from app.services import config_store
from app.db import init_db
from contextlib import asynccontextmanager


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()  # 启动时建评估元数据表（幂等）
    config_store.load_overrides()  # 应用解析/物理常数运行时覆盖（若有）
    yield


app = FastAPI(title="组合动力智能评估", version="0.2.0", lifespan=lifespan)

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

# 评估平台 v2：切片快照预览目录
from app.settings import settings as _settings
_settings.previews_dir.mkdir(parents=True, exist_ok=True)
app.mount("/previews", StaticFiles(directory=str(_settings.previews_dir)), name="previews")

from app.core.qjz_fluent_post.http_api import create_fluent_router
fluent_router = create_fluent_router(ROOT)
app.include_router(fluent_router)
app.include_router(files_router.router)
app.include_router(charts_router.router)
app.include_router(diagnose_router.router)
app.include_router(vlm_router.router)
app.include_router(ragflow_router.router)
app.include_router(models_config_router.router)
# 评估平台 v2 路由
# analysis 先于 library：analysis 的字面路由（/cases/sim-compare 等）需优先于
# library 的 /cases/{case_id:int}，否则 "sim-compare" 会被当作 case_id 触发 422。
app.include_router(analysis_router.router)
app.include_router(library_router.router)
app.include_router(compare_router.router)
app.include_router(agent_router.router)
app.include_router(report_router.router)
app.include_router(knowledge_router.router)
app.include_router(search_router.router)
app.include_router(llm_config_router.router)
app.include_router(chat_v2_router.router)
app.include_router(config_router.router)
app.include_router(fs_router.router)
app.include_router(formulas_router.router)


@app.get("/")
async def index():
    """主页面"""
    return FileResponse(ROOT / "static" / "index.html")


@app.get("/help")
async def docs_page():
    """使用文档页面"""
    return FileResponse(ROOT / "static" / "docs.html")


@app.get("/platform")
async def platform_page():
    """评估平台新界面（原型演进，接 v2 API）。"""
    return FileResponse(ROOT / "docs" / "组合动力智能评估-原型.html")


if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8501, reload=True)
