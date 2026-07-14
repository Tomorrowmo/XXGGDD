"""判据服务 —— 读 sim-knowledge 判据库 + 试验异常判据（升级自 llm_client 写死版）。

对齐 docs/01 §4.5：llm_client 里 min<0 / max>10 / std>mean×2 三条写死规则，
在此结构化为可配置判据；仿真域判据读 sim-knowledge/physics/<域>/criteria.yaml。
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from app.settings import settings

try:
    import yaml  # pyyaml
except ImportError:  # 优雅降级，缺依赖时仍可用内置默认
    yaml = None


# --------------------------------------------------------------------------- 偏差分级 → 评级
# 对齐原型知识库实例《评估规范 v2.1》：≤3优秀 / 3-5合格 / 5-10复核 / >10不合格
DEVIATION_TIERS: list[tuple[float, str]] = [
    (3.0, "优秀"), (5.0, "合格"), (10.0, "需复核"), (math.inf, "不合格"),
]


def tier_from_deviation(abs_dev_pct: float) -> str:
    for thresh, label in DEVIATION_TIERS:
        if abs_dev_pct <= thresh:
            return label
    return "不合格"


def grade_from_avg_deviation(avg_abs_dev_pct: float, all_qoi_pass: bool = True) -> str:
    """由平均绝对偏差聚合出综合评级（L1）。权重方案可后续配置化。"""
    if avg_abs_dev_pct <= 1.5 and all_qoi_pass:
        return "A"
    if avg_abs_dev_pct <= 2.0:
        return "A-"
    if avg_abs_dev_pct <= 3.5:
        return "B+"
    if avg_abs_dev_pct <= 6.0:
        return "B"
    if avg_abs_dev_pct <= 10.0:
        return "C+"
    return "C"


# --------------------------------------------------------------------------- 试验异常判据（结构化）
@dataclass
class CriterionHit:
    intent: str
    label: str
    detail: str
    severity: str          # anomaly / warning
    reference: str | None = None


def check_experiment_anomalies(stats: list[dict]) -> list[CriterionHit]:
    """逐通道扫描（阈值读 settings，非写死）——升级自 llm_client 三条规则。"""
    rng = settings.experiment.pressure_valid_range_mpa
    hits: list[CriterionHit] = []
    for s in stats:
        cat = s.get("category", "")
        if cat not in ("流道压力", "室压", "隔离段"):
            continue
        if s["min"] < 0:
            hits.append(CriterionHit("is_negative_pressure", s["label"],
                                     f"最小值 {s['min']:.4f} MPa < 0（已加大气压修正，负压异常）", "anomaly"))
        if s["max"] > rng[1]:
            hits.append(CriterionHit("is_over_range", s["label"],
                                     f"最大值 {s['max']:.4f} MPa > {rng[1]} MPa（超常规范围）", "warning"))
        if s["mean"] > 0.01 and s["std"] > s["mean"] * 2:
            hits.append(CriterionHit("is_excessive_fluctuation", s["label"],
                                     f"标准差 {s['std']:.4f} > 均值×2（波动异常剧烈）", "warning"))
    return hits


# --------------------------------------------------------------------------- sim-knowledge 判据加载
@lru_cache(maxsize=32)
def load_domain_criteria(domain: str) -> dict:
    """读 sim-knowledge/physics/<域>/criteria.yaml（护城河判据）。缺失则返回空。"""
    if yaml is None:
        return {}
    path: Path = settings.assets.criteria_dir / domain / "criteria.yaml"
    if not path.exists():
        return {}
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}


def list_available_domains() -> list[str]:
    root = settings.assets.criteria_dir
    if not root.exists():
        return []
    return sorted(p.name for p in root.iterdir() if p.is_dir())
