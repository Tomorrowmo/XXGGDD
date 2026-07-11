"""集中路径常量，全项目共享。app/config.py 位于 <项目根>/app/，故 ROOT 为其上两级。"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
STATIC_DIR = ROOT / "static"
RESULTS_PNG_DIR = ROOT / "results_png"
CASE_DIR = (ROOT / "Case").resolve()
OUTPUT_PLOTS_DIR = (ROOT / "output_plots").resolve()
WORKSPACE_DIR = ROOT / "workspace"  # 阶段 B agent 工作区，阶段 A 先声明不使用
