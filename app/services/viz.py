"""切片/云图可视化适配器 —— 平台自有的纯标准 VTK 渲染生成切片快照。

渲染代码已 vendored 进平台（app/services/render/*），**不再依赖 SimGraph2 仓库**。
OpenFOAM 算例只需一个装了 VTK 的 python——平台基础环境（VTK 9.6+）即可，故默认用
当前解释器（sys.executable），完全自洽。需 Romtek 的格式（Fluent .cas.h5 等）才回退
到 PostProcessTool 环境（POSTPROCESS_PYTHON）。渲染仍走**子进程**隔离，避免 VTK
离屏渲染污染服务进程；缺环境时优雅降级 available=False。
"""
from __future__ import annotations

import glob
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from app.settings import settings


def _render_source(case_path: str | Path) -> str:
    """Romtek/VTK 的 C++ 读取器在 Windows 上打不开含中文/非 ASCII 的路径（"file not found"）。

    路径非 ASCII 时，把算例文件复制到平台内的 ASCII 缓存目录再返回该路径（文件名多为 ASCII，
    只是父目录含中文）。传统 .cas / .cas.h5 会一并复制其 .dat 伴随文件。目录型(OpenFOAM)一般 ASCII，原样返回。
    """
    p = Path(case_path)
    if str(p).isascii():
        return str(p)
    if p.is_dir():
        return str(p)   # OpenFOAM 目录通常 ASCII；非 ASCII 目录暂不处理
    cache = settings.previews_dir / "_srccache" / hashlib.sha1(str(p.resolve()).encode()).hexdigest()[:12]
    fname = p.name if p.name.isascii() else ("case" + p.suffix.lower())
    dst = cache / fname
    if not dst.exists():
        cache.mkdir(parents=True, exist_ok=True)
        shutil.copy2(p, dst)
        # 复制同基名的场数据伴随文件
        for a, b in ((".cas", ".dat"), (".cas.h5", ".dat.h5"), (".cas.gz", ".dat.gz")):
            low = p.name.lower()
            if low.endswith(a):
                comp = p.with_name(p.name[: -len(a)] + b)
                if comp.exists():
                    shutil.copy2(comp, cache / (comp.name if comp.name.isascii() else ("case" + b)))
    return str(dst)

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


def generate_vtp(case_path: str | Path, *, timeout: int = 240) -> dict:
    """导出边界面 VTP（供前端 vtk.js 真三维交互）。已缓存则直接返回。"""
    out = preview_dir(case_path)
    key = out.name
    if (out / "surface.vtp").exists() and (out / "meta.json").exists():
        try:
            meta = json.loads((out / "meta.json").read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            meta = {}
        return {"available": True, "cached": True,
                "vtp_url": f"/previews/{key}/surface.vtp",
                "meta_url": f"/previews/{key}/meta.json",
                "scalars": [s.get("name") for s in meta.get("scalars", [])],
                "n_points": meta.get("n_points"), "n_cells": meta.get("n_cells")}
    if not _env_ready(case_path):
        return {"available": False, "reason": "该格式需 Romtek 渲染环境"}
    runner = Path(__file__).with_name("render_runner.py")
    env = {**os.environ, "SIMGRAPH2_ROOT": str(settings.assets.simgraph2_root)}
    try:
        proc = subprocess.run(
            [_render_python(case_path), str(runner), _render_source(case_path), str(out), "vtp"],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout, env=env)
    except subprocess.TimeoutExpired:
        return {"available": False, "reason": "VTP 导出超时"}
    res = _parse_last_json(proc.stdout)
    if not res or not res.get("ok"):
        return {"available": False, "reason": (res or {}).get("error") or "VTP 导出失败"}
    return {"available": True, "cached": False,
            "vtp_url": f"/previews/{key}/surface.vtp",
            "meta_url": f"/previews/{key}/meta.json",
            "scalars": res.get("scalars", []),
            "n_points": res.get("n_points"), "n_cells": res.get("n_cells"),
            "engine": res.get("engine")}


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
            [_render_python(case_path), str(runner), _render_source(case_path), str(out), f"turntable:{n_frames}"],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout, env=env)
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
            [_render_python(case_path), str(runner), _render_source(case_path), str(out), scalar],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout, env=env,
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
