"""服务器文件浏览 API（v2）—— 供入库路径选择器用（从资源管理器式界面选服务器上的路径）。

单租户内网工具，按用户选择开放整机盘符浏览。只读，不改动文件系统。
"""
from __future__ import annotations

import os
import string
from pathlib import Path

from fastapi import APIRouter, HTTPException

from app.services.ingest import detect_kind

router = APIRouter(prefix="/api/v2/fs", tags=["fs"])

_MAX_ENTRIES = 1000


def _drives() -> list[str]:
    """Windows 盘符列表；非 Windows 返回 ['/']。"""
    if os.name != "nt":
        return ["/"]
    out = []
    for c in string.ascii_uppercase:
        d = f"{c}:/"
        if os.path.exists(d):
            out.append(d)
    return out


def _kind_of(p: Path) -> str | None:
    try:
        k = detect_kind(p)
    except Exception:  # noqa: BLE001
        return None
    return k.value if k else None


@router.get("/list")
def fs_list(path: str = ""):
    """列目录。path 为空→返回盘符根列表。返回 {path, parent, drives, entries[]}。

    entry: {name, path, is_dir, ingestable(bool), kind(experiment/simulation/None), size}
    """
    drives = _drives()
    # 空路径：给盘符（Windows）/根（POSIX）
    if not path or path in ("", "/"):
        if os.name == "nt" and (not path or path == ""):
            entries = [{"name": d, "path": d, "is_dir": True, "ingestable": False,
                        "kind": None, "size": None} for d in drives]
            return {"path": "", "parent": None, "drives": drives, "entries": entries}
        path = path or "/"

    p = Path(path)
    if not p.exists():
        raise HTTPException(404, f"路径不存在：{path}")
    if not p.is_dir():
        # 传入文件 → 返回其所在目录
        p = p.parent

    entries = []
    truncated = False
    try:
        items = sorted(p.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower()))
    except PermissionError:
        raise HTTPException(403, f"无权限访问：{path}")
    except OSError as e:  # noqa: BLE001
        raise HTTPException(400, f"无法访问：{e}")

    for it in items:
        if len(entries) >= _MAX_ENTRIES:
            truncated = True
            break
        try:
            is_dir = it.is_dir()
        except OSError:
            continue
        kind = _kind_of(it)
        size = None
        if not is_dir:
            try:
                size = it.stat().st_size
            except OSError:
                size = None
        # 目录本身可能是 OpenFOAM 算例（kind=simulation 且 is_dir）→ 可整目录入库
        entries.append({
            "name": it.name, "path": str(it).replace("\\", "/"),
            "is_dir": is_dir, "ingestable": kind is not None,
            "kind": kind, "size": size,
        })

    parent = str(p.parent).replace("\\", "/") if p.parent != p else None
    # 到盘符根（如 D:/）时，parent 给空串→回到盘符选择
    if os.name == "nt" and p.parent == p:
        parent = ""
    return {"path": str(p).replace("\\", "/"), "parent": parent,
            "drives": drives, "entries": entries, "truncated": truncated}
