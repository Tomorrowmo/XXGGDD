"""切片/云图可视化适配器 —— 平台自有的纯标准 VTK 渲染生成切片快照。

渲染代码已 vendored 进平台（app/services/render/*），**不再依赖 SimGraph2 仓库**。
OpenFOAM 算例只需一个装了 VTK 的 python——平台基础环境（VTK 9.6+）即可，故默认用
当前解释器（sys.executable），完全自洽。需 Romtek 的格式（Fluent .cas.h5 等）才回退
到 PostProcessTool 环境（POSTPROCESS_PYTHON）。渲染仍走**子进程**隔离，避免 VTK
离屏渲染污染服务进程；缺环境时优雅降级 available=False。
"""
from __future__ import annotations

import glob
import json
import os
import subprocess
import sys
from pathlib import Path

from app.settings import settings

# simagent_render 产出的图名
SLICE_NAMES = ["slice_X", "slice_Y", "slice_Z", "surf_a", "surf_b"]


def _is_openfoam(case_path: str | Path) -> bool:
    p = Path(case_path)
    if str(p).lower().endswith(".foam"):
        return True
    if p.is_dir():
        return (p / "system" / "controlDict").exists() or bool(glob.glob(str(p / "*.foam")))
    return False


def _render_python(case_path: str | Path) -> str:
    """选渲染用的 python：OpenFOAM 用基础环境（含 VTK，自洽）；
    需 Romtek 的格式优先 PostProcessTool，缺则退回基础环境（届时诚实报错）。"""
    if _is_openfoam(case_path):
        return sys.executable
    ppt = settings.assets.postprocess_python
    return str(ppt) if ppt and Path(ppt).exists() else sys.executable


def preview_dir(case_path: str | Path) -> Path:
    """路径 → 标准化预览目录（命名对齐 SimGraph2：<parent>_<name>）。"""
    p = Path(case_path)
    key = f"{p.parent.name}_{p.stem}"
    d = settings.previews_dir / key
    d.mkdir(parents=True, exist_ok=True)
    return d


def _env_ready(case_path: str | Path | None = None) -> bool:
    """渲染是否可用。OpenFOAM：基础环境有 VTK 即可（几乎总为真）；
    其它需 Romtek 的格式：要 PostProcessTool + SimGraph2 才行。"""
    if case_path is not None and _is_openfoam(case_path):
        return True  # 用 sys.executable（基础环境已含 VTK）
    py = settings.assets.postprocess_python
    return Path(py).exists() and settings.assets.simgraph2_root.exists()


def available(case_path: str | Path | None = None) -> bool:
    return _env_ready(case_path)


def cached_previews(case_path: str | Path) -> dict:
    """只读已缓存的切片（不触发渲染）—— 供列表缩略图快速取用。"""
    out = preview_dir(case_path)
    images = {n: f"{n}.png" for n in SLICE_NAMES if (out / f"{n}.png").exists()}
    return {"available": bool(images), "dir": str(out), "images": images}


def generate_turntable(case_path: str | Path, n_frames: int = 24, *, timeout: int = 240) -> dict:
    """生成绕轴 n 帧转台图（供前端拖拽轨道旋转）。已缓存则直接返回。"""
    out = preview_dir(case_path)
    key = out.name
    cached = sorted(p.name for p in out.glob("turn_*.png"))
    if cached:
        return {"available": True, "frames": len(cached),
                "urls": [f"/previews/{key}/{fn}" for fn in cached], "cached": True}
    if not _env_ready(case_path):
        return {"available": False, "reason": "该格式需 Romtek 渲染环境（PostProcessTool + SimGraph2）"}
    runner = Path(__file__).with_name("render_runner.py")
    env = {**os.environ, "SIMGRAPH2_ROOT": str(settings.assets.simgraph2_root)}
    try:
        proc = subprocess.run(
            [_render_python(case_path), str(runner), str(case_path), str(out), f"turntable:{n_frames}"],
            capture_output=True, text=True, timeout=timeout, env=env)
    except subprocess.TimeoutExpired:
        return {"available": False, "reason": "转台渲染超时"}
    res = _parse_last_json(proc.stdout)
    if not res or not res.get("ok"):
        return {"available": False, "reason": (res or {}).get("error") or "转台渲染失败"}
    frames = sorted(res.get("images", []))
    return {"available": True, "frames": len(frames),
            "urls": [f"/previews/{key}/{fn}" for fn in frames],
            "engine": res.get("engine"), "cached": False}


def generate_previews(case_path: str | Path, scalar: str = "T", *, timeout: int = 180) -> dict:
    """为算例生成切片快照（子进程调 PostProcessTool 渲染）。

    返回 {available, dir, images:{name:filename}, scalar?, reason?}。已有则直接返回缓存。
    """
    out = preview_dir(case_path)
    cached = {n: f"{n}.png" for n in SLICE_NAMES if (out / f"{n}.png").exists()}
    if cached:
        return {"available": True, "dir": str(out), "images": cached, "cached": True}

    if not _env_ready(case_path):
        return {"available": False, "dir": str(out), "images": {},
                "reason": "该格式需 Romtek 渲染环境（PostProcessTool + SimGraph2），当前不可用"}

    runner = Path(__file__).with_name("render_runner.py")
    # SIMGRAPH2_ROOT 仅供 Romtek 回退用；OpenFOAM 走 vendored 代码不需要
    env = {**os.environ, "SIMGRAPH2_ROOT": str(settings.assets.simgraph2_root)}
    try:
        proc = subprocess.run(
            [_render_python(case_path), str(runner), str(case_path), str(out), scalar],
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
            "scalar": result.get("scalar"), "engine": result.get("engine"),
            "cached": False}


def _parse_last_json(text: str) -> dict | None:
    for line in reversed((text or "").strip().splitlines()):
        line = line.strip()
        if line.startswith("{") and line.endswith("}"):
            try:
                return json.loads(line)
            except json.JSONDecodeError:
                continue
    return None
