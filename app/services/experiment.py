"""可配置的试验数据解析服务 —— 重构自 app/core/plotter.py，去写死。

对齐 docs/01 §3 写死点：headerIndex / 分隔符 / 通道正则 / 大气压修正 全部读 settings。
新增（对齐原型 试验分析详细设计）：
    - 通道分类识别（流道/室压/隔离段/壁温/流量）
    - 阶段分割（点火/建压/主级稳态/关车）
    - 稳态段关键量提取 → 供对比评估作实验真值
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from app.settings import settings


# --------------------------------------------------------------------------- 解析
@dataclass
class ParsedExperiment:
    time: np.ndarray                 # (N,) 时间列
    channels: list[dict]             # [{index, label, category}]
    data: np.ndarray                 # (N, C) 全部列
    n_rows: int
    headers: list[str]


def _classify_channel(label: str) -> str:
    if re.match(r"流道", label):
        return "流道压力"
    if re.match(r"室压", label):
        return "室压"
    if re.match(r"隔离段", label):
        return "隔离段"
    if re.match(r"壁温", label):
        return "壁温"
    if re.match(r"流量", label):
        return "流量"
    return "其它"


def read_experiment(path: str | Path) -> ParsedExperiment:
    """按 settings.experiment 配置解析试验 TXT/CSV（不再写死 headerIndex/分隔符）。"""
    cfg = settings.experiment
    path = Path(path)
    lines = path.read_text(encoding=cfg.encoding, errors="replace").splitlines()
    if len(lines) <= cfg.header_index:
        raise ValueError(f"文件行数不足，headerIndex={cfg.header_index} 越界：{path.name}")

    headers = [h.strip() for h in lines[cfg.header_index].split(cfg.delimiter)]
    rows = []
    for ln in lines[cfg.header_index + 1:]:
        if not ln.strip():
            continue
        parts = ln.split(cfg.delimiter)
        try:
            rows.append([float(p) if p.strip() not in ("", "nan", "NaN") else np.nan for p in parts])
        except ValueError:
            continue
    data = np.array(rows, dtype=float)

    channels = extract_channels(headers)
    time = data[:, cfg.time_column] if data.size else np.array([])
    return ParsedExperiment(time=time, channels=channels, data=data, n_rows=len(data), headers=headers)


def extract_channels(headers: list[str]) -> list[dict]:
    """按可配置正则集提取通道（原 plotter 只认 流道\\d+）。"""
    patterns = [re.compile(p) for p in settings.experiment.channel_patterns]
    out = []
    for idx, h in enumerate(headers):
        h = h.strip()
        if any(p.search(h) for p in patterns):
            out.append({"index": idx, "label": h, "category": _classify_channel(h)})
    return out


# --------------------------------------------------------------------------- 统计
def compute_stats(parsed: ParsedExperiment) -> list[dict]:
    """各通道 min/max/mean/std（加大气压修正，修正量可配置）。"""
    corr = settings.experiment.atmos_correction_mpa
    out = []
    for ch in parsed.channels:
        col = parsed.data[:, ch["index"]]
        # 压力类加大气压修正；温度/流量不修正
        if ch["category"] in ("流道压力", "室压", "隔离段"):
            col = col + corr
        valid = col[~np.isnan(col)]
        if valid.size == 0:
            continue
        out.append({
            "label": ch["label"], "category": ch["category"],
            "min": round(float(valid.min()), 6), "max": round(float(valid.max()), 6),
            "mean": round(float(valid.mean()), 6), "std": round(float(valid.std()), 6),
            "count": int(valid.size),
        })
    return out


# --------------------------------------------------------------------------- 阶段分割
@dataclass
class Phases:
    ignition: tuple[float, float]     # 点火
    buildup: tuple[float, float]      # 建压
    steady: tuple[float, float]       # 主级稳态（取值区）
    shutdown: tuple[float, float]     # 关车


def segment_phases(parsed: ParsedExperiment, ref_channel: str | None = None) -> Phases:
    """按参考压力通道自动切分四阶段（简单包络法，稳态=压力平台段）。

    默认取第一个室压/流道通道作参考；找压力上升沿=建压结束、下降沿=关车开始。
    """
    if parsed.time.size == 0:
        return Phases((0, 0), (0, 0), (0, 0), (0, 0))
    t = parsed.time
    # 选参考通道
    ref = None
    for ch in parsed.channels:
        if ref_channel and ch["label"] == ref_channel:
            ref = ch["index"]; break
        if ch["category"] in ("室压", "流道压力"):
            ref = ch["index"]; break
    if ref is None:
        ref = parsed.channels[0]["index"] if parsed.channels else 1
    p = parsed.data[:, ref]
    p = np.nan_to_num(p, nan=0.0)
    hi = np.nanmax(p)
    thresh = 0.5 * hi                      # 半高判定主级
    above = p > thresh
    if not above.any():
        return Phases((float(t[0]), float(t[-1])), (0, 0), (0, 0), (0, 0))
    i0, i1 = int(np.argmax(above)), int(len(above) - 1 - np.argmax(above[::-1]))
    # 建压=上升沿附近 0.3高→0.9高；稳态=中段收缩 10%
    span = i1 - i0
    s0, s1 = i0 + int(0.12 * span), i1 - int(0.06 * span)
    return Phases(
        ignition=(float(t[0]), float(t[i0])),
        buildup=(float(t[i0]), float(t[s0])),
        steady=(float(t[s0]), float(t[s1])),
        shutdown=(float(t[i1]), float(t[-1])),
    )


# --------------------------------------------------------------------------- 关键量提取（真值）
def extract_steady_qoi(parsed: ParsedExperiment, phases: Phases) -> list[dict]:
    """从主级稳态段提取关键量 → 供对比评估作实验真值。

    返回 [{quantity, value, unit, method, channel}]，压力已加大气压修正。
    """
    corr = settings.experiment.atmos_correction_mpa
    t = parsed.time
    if t.size == 0:
        return []
    m = (t >= phases.steady[0]) & (t <= phases.steady[1])
    out = []
    for ch in parsed.channels:
        col = parsed.data[:, ch["index"]]
        cat = ch["category"]
        if cat in ("流道压力", "室压", "隔离段"):
            col = col + corr
            unit = "MPa"
        elif cat == "壁温":
            unit = "K"
        elif cat == "流量":
            unit = "kg/s"
        else:
            unit = ""
        seg = col[m]
        seg = seg[~np.isnan(seg)]
        if seg.size == 0:
            continue
        # 壁压峰值取全程 max（col 已含大气压修正）；其余取稳态段均值
        if cat in ("流道压力", "隔离段"):
            value, method = float(np.nanmax(col)), "全程峰值"
        else:
            value, method = float(seg.mean()), "稳态段均值"
        out.append({"quantity": ch["label"], "value": round(value, 4),
                    "unit": unit, "method": method, "channel": ch["label"], "category": cat})
    return out
