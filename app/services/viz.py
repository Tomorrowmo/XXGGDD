"""切片/云图可视化适配器 —— 用 SimGraph2 的纯标准 VTK 渲染生成切片快照。

渲染依赖 VTK+Romtek，只在 PostProcessTool 环境可用；故通过**子进程**调该环境的
python 跑 render_runner.py（SimGraph2 的分离式后处理设计），主程序可在任意环境运行。
缺环境时优雅降级 available=False。
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

from app.settings import settings

# simagent_render 产出的图名
SLICE_NAMES = ["slice_X", "slice_Y", "slice_Z", "surf_a", "surf_b"]


def preview_dir(case_path: str | Path) -> Path:
    """路径 → 标准化预览目录（命名对齐 SimGraph2：<parent>_<name>）。"""
    p = Path(case_path)
    key = f"{p.parent.name}_{p.stem}"
    d = settings.previews_dir / key
    d.mkdir(parents=True, exist_ok=True)
    return d


def _env_ready() -> bool:
    py = settings.assets.postprocess_python
    return Path(py).exists() and settings.assets.simgraph2_root.exists()


def available() -> bool:
    return _env_ready()


def generate_previews(case_path: str | Path, scalar: str = "T", *, timeout: int = 180) -> dict:
    """为算例生成切片快照（子进程调 PostProcessTool 渲染）。

    返回 {available, dir, images:{name:filename}, scalar?, reason?}。已有则直接返回缓存。
    """
    out = preview_dir(case_path)
    cached = {n: f"{n}.png" for n in SLICE_NAMES if (out / f"{n}.png").exists()}
    if cached:
        return {"available": True, "dir": str(out), "images": cached, "cached": True}

    if not _env_ready():
        return {"available": False, "dir": str(out), "images": {},
                "reason": "PostProcessTool/SimGraph2 渲染环境不可用"}

    runner = Path(__file__).with_name("render_runner.py")
    env = {**os.environ, "SIMGRAPH2_ROOT": str(settings.assets.simgraph2_root)}
    try:
        proc = subprocess.run(
            [str(settings.assets.postprocess_python), str(runner),
             str(case_path), str(out), scalar],
            capture_output=True, text=True, timeout=timeout, env=env,
        )
    except subprocess.TimeoutExpired:
        return {"available": False, "dir": str(out), "images": {}, "reason": "渲染超时"}

    result = _parse_last_json(proc.stdout)
    if not result or not result.get("ok"):
        reason = (result or {}).get("error") or (proc.stderr[-200:] if proc.stderr else "渲染失败")
        return {"available": False, "dir": str(out), "images": {}, "reason": reason}

    images = {Path(f).stem: f for f in result.get("images", [])}
    return {"available": True, "dir": str(out), "images": images,
            "scalar": result.get("scalar"), "cached": False}


def _parse_last_json(text: str) -> dict | None:
    for line in reversed((text or "").strip().splitlines()):
        line = line.strip()
        if line.startswith("{") and line.endswith("}"):
            try:
                return json.loads(line)
            except json.JSONDecodeError:
                continue
    return None
