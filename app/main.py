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
app.include_router(ragflow_router.router)
app.include_router(models_config_router.router)


@app.get("/")
async def index():
    """主页面"""
    return FileResponse(ROOT / "static" / "index.html")


@app.get("/help")
async def docs_page():
    """使用文档页面"""
    return FileResponse(ROOT / "static" / "docs.html")


if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8501, reload=True)
