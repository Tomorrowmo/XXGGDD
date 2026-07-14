"""simparse 解析引擎适配器 —— 复用 simcli 的 sim-parse 包（CFD/CAE 分层解析）。

策略：把 settings.assets.simparse_pkg 加入 sys.path 直接 import（进程内，最快）；
不可用时优雅降级返回 {"available": False}，不拖垮平台。
覆盖：summary / convergence / qoi / field_stats / mesh_zones。
"""
from __future__ import annotations

import sys
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.settings import settings


@lru_cache(maxsize=1)
def _load_sim_parse():
    """惰性载入 sim_parse；失败返回 None。"""
    pkg = settings.assets.simparse_pkg
    try:
        if pkg.exists() and str(pkg) not in sys.path:
            sys.path.insert(0, str(pkg))
        import sim_parse  # type: ignore
        return sim_parse
    except Exception:
        return None


def available() -> bool:
    return _load_sim_parse() is not None


@lru_cache(maxsize=64)
def _parse(case_path: str) -> Any:
    sp = _load_sim_parse()
    if sp is None:
        return None
    fn = getattr(sp, "parse_case", None) or getattr(sp, "parse", None)
    if not callable(fn):
        return None
    try:
        return fn(case_path, target_tier=5)   # tier5 含 QOI
    except TypeError:
        try:
            return fn(case_path)
        except Exception:
            return None
    except Exception:
        return None


def _tier(parsed: Any, *suffixes: str) -> Any:
    """按 tier 后缀取子块（sim_parse 键形如 tier_3_metadata / tier_5_qoi）。"""
    if not isinstance(parsed, dict):
        return None
    for suf in suffixes:
        if suf in parsed:
            return parsed[suf]
        for k, v in parsed.items():
            if k.endswith("_" + suf) or k == suf:
                return v
    return None


_CONV_HINTS = ("converg", "residual", "diverg", "steady", "nan", "courant")


def summary(case_path: str) -> dict:
    """算例概况（tier_3_metadata + tier_1_identify）。"""
    if not available():
        return {"available": False, "reason": "sim-parse 未安装或路径未配置"}
    parsed = _parse(case_path)
    if parsed is None:
        return {"available": False, "reason": "解析失败"}
    meta = _tier(parsed, "metadata") or {}
    ident = _tier(parsed, "identify") or {}
    merged = {**(ident if isinstance(ident, dict) else {}),
              **(meta if isinstance(meta, dict) else {})}
    return {"available": bool(merged) or not parsed.get("errors"),
            "summary": merged, "case_path": case_path}


def convergence(case_path: str) -> dict:
    """从 tier_5_qoi 过滤收敛相关判据量。"""
    if not available():
        return {"available": False}
    parsed = _parse(case_path)
    q = _tier(parsed, "qoi") or []
    conv = [x for x in q if isinstance(x, dict)
            and any(h in str(x.get("variable", "")).lower() for h in _CONV_HINTS)]
    return {"available": parsed is not None, "convergence": conv}


def qoi(case_path: str) -> dict:
    """Tier5 QOI 长表（variable/value/unit/status/confidence）。只保留有值项。"""
    if not available():
        return {"available": False}
    parsed = _parse(case_path)
    items = _tier(parsed, "qoi") or []
    valued = [x for x in items if isinstance(x, dict) and x.get("value") is not None]
    return {"available": parsed is not None, "qoi": valued}


def field_stats(case_path: str) -> dict:
    if not available():
        return {"available": False}
    parsed = _parse(case_path)
    return {"available": parsed is not None,
            "field_stats": _tier(parsed, "field_stats") or {}}


def mesh_zones(case_path: str) -> dict:
    if not available():
        return {"available": False}
    parsed = _parse(case_path)
    return {"available": parsed is not None,
            "mesh_zones": _tier(parsed, "inventory") or {}}


def clear_cache() -> None:
    _parse.cache_clear()
