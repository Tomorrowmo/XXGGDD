"""解析 / 物理常数 配置的读写与持久化（去写死配置项的运行时覆盖）。

设计对齐 llm_config：默认值来自 settings（代码/环境变量），运行时可在配置页
改写少量安全字段并落 parse_config.json；启动时 load_overrides() 应用回 settings。
判据部分只读——真值来自 sim-knowledge 护城河仓库（criteria.yaml），此处仅汇报来源。
"""
from __future__ import annotations

import glob
import json
import os
from pathlib import Path
from typing import Any

from app.settings import settings

# 允许运行时改写的字段（白名单，避免暴露路径/密钥等）
_EXP_FIELDS = ("delimiter", "encoding", "header_index", "time_column",
               "channel_patterns", "atmos_correction_mpa")
_PHYS_FIELDS = ("gamma", "gas_constant")


def _override_path() -> Path:
    return settings.parse_config_file


def criteria_info() -> dict:
    """判据来源概况（只读，来自 sim-knowledge 护城河）。"""
    sk = settings.assets.sim_knowledge
    domains: list[str] = []
    if sk.exists():
        for c in glob.glob(str(sk / "**" / "criteria.yaml"), recursive=True):
            domains.append(os.path.basename(os.path.dirname(c)))
    return {"source": str(sk), "exists": sk.exists(),
            "n_domains": len(domains), "domains": sorted(domains)}


def get_config() -> dict:
    exp = settings.experiment
    phys = settings.physics
    return {
        "experiment": {
            "delimiter": exp.delimiter,
            "encoding": exp.encoding,
            "header_index": exp.header_index,
            "time_column": exp.time_column,
            "channel_patterns": list(exp.channel_patterns),
            "atmos_correction_mpa": exp.atmos_correction_mpa,
            "pressure_valid_range_mpa": list(exp.pressure_valid_range_mpa),
        },
        "physics": {"gamma": phys.gamma, "gas_constant": phys.gas_constant},
        "criteria": criteria_info(),
        "editable": {"experiment": list(_EXP_FIELDS), "physics": list(_PHYS_FIELDS)},
        "override_file": str(_override_path()),
    }


def _apply(exp_patch: dict, phys_patch: dict) -> None:
    """把补丁应用到内存 settings（仅白名单字段）。"""
    for k in _EXP_FIELDS:
        if k in exp_patch and exp_patch[k] is not None:
            setattr(settings.experiment, k, exp_patch[k])
    for k in _PHYS_FIELDS:
        if k in phys_patch and phys_patch[k] is not None:
            setattr(settings.physics, k, phys_patch[k])


def update_config(patch: dict) -> dict:
    """校验并应用配置补丁，落盘持久化。返回更新后的完整配置。"""
    exp_patch = dict(patch.get("experiment") or {})
    phys_patch = dict(patch.get("physics") or {})
    # 轻校验
    if "header_index" in exp_patch and exp_patch["header_index"] is not None:
        hi = int(exp_patch["header_index"])
        if hi < 0:
            raise ValueError("header_index 不能为负")
        exp_patch["header_index"] = hi
    if "channel_patterns" in exp_patch and exp_patch["channel_patterns"] is not None:
        pats = exp_patch["channel_patterns"]
        if isinstance(pats, str):
            pats = [p.strip() for p in pats.split("|") if p.strip()]
        if not isinstance(pats, list) or not pats:
            raise ValueError("channel_patterns 需为非空列表或用 | 分隔的字符串")
        import re
        for p in pats:
            try:
                re.compile(p)  # 校验正则合法
            except re.error as e:
                raise ValueError(f"通道正则非法：{p}（{e}）")
        exp_patch["channel_patterns"] = pats
    if "atmos_correction_mpa" in exp_patch and exp_patch["atmos_correction_mpa"] is not None:
        exp_patch["atmos_correction_mpa"] = float(exp_patch["atmos_correction_mpa"])
    if "gamma" in phys_patch and phys_patch["gamma"] is not None:
        phys_patch["gamma"] = float(phys_patch["gamma"])
    if "gas_constant" in phys_patch and phys_patch["gas_constant"] is not None:
        phys_patch["gas_constant"] = float(phys_patch["gas_constant"])

    _apply(exp_patch, phys_patch)
    _persist()
    return get_config()


def _persist() -> None:
    exp = settings.experiment
    phys = settings.physics
    data = {
        "experiment": {k: getattr(exp, k) for k in _EXP_FIELDS},
        "physics": {k: getattr(phys, k) for k in _PHYS_FIELDS},
    }
    p = _override_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def load_overrides() -> None:
    """启动时调用：若存在覆盖文件则应用回 settings。"""
    p = _override_path()
    if not p.exists():
        return
    try:
        data: dict[str, Any] = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return
    _apply(dict(data.get("experiment") or {}), dict(data.get("physics") or {}))
