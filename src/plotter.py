"""
交互式图表生成模块
基于 Plotly + 用户上传数据，输出 JSON 供前端 Plotly.js 渲染
"""
import re
import numpy as np
import plotly.graph_objects as go
from pathlib import Path
from A00_parameterData import headerIndex

MAX_POINTS = 2000  # 降采样上限
DATA_DIR = Path(__file__).parent.parent / "data"


# ---------------------------------------------------------------------------
# 数据读取
# ---------------------------------------------------------------------------
def _read_file(filepath: Path):
    """读取逗号分隔的 txt 数据文件，返回 (header_list, data_2d_array)"""
    lines = []
    with open(filepath, "r", encoding="utf-8", errors="replace") as f:
        for row in f:
            lines.append(row)

    header_line = lines[headerIndex].strip()
    headers = [h.strip() for h in header_line.split(",")]

    data_rows = []
    for i in range(headerIndex + 1, len(lines)):
        parts = lines[i].split(",")
        if len(parts) >= len(headers):
            data_rows.append(parts[:len(headers)])

    arr = np.zeros((len(data_rows), len(headers)))
    for i, row in enumerate(data_rows):
        for j in range(len(headers)):
            try:
                arr[i, j] = float(row[j])
            except (ValueError, IndexError):
                arr[i, j] = np.nan

    return headers, arr


# ---------------------------------------------------------------------------
# 通道提取
# ---------------------------------------------------------------------------
def extract_channels(headers: list) -> list:
    """
    从 header 列表中提取所有包含「流道」的列
    label 简化规则：从原始名称中提取「流道\d+」
    """
    channels = []
    for i, h in enumerate(headers):
        m = re.search(r"流道\d+(?:\.\d+)?", h)
        if m:
            channels.append({"index": i, "label": m.group(), "header": h})
    return channels


# ---------------------------------------------------------------------------
# 统计计算
# ---------------------------------------------------------------------------
def compute_channel_stats(filename: str):
    """
    计算所有流道通道的均值、最小值、最大值、方差、标准差
    返回 {stats: [...], channel_count, data_rows}
    """
    filepath = DATA_DIR / filename
    if not filepath.exists():
        raise FileNotFoundError(f"文件 {filename} 不存在")

    headers, data = _read_file(filepath)
    channels = extract_channels(headers)

    stats_list = []
    for ch in channels:
        col = data[:, ch["index"]] + 0.101325
        valid = col[~np.isnan(col)]
        if len(valid) < 1:
            continue
        stats_list.append({
            "label": ch["label"],
            "mean": round(float(np.mean(valid)), 6),
            "min": round(float(np.min(valid)), 6),
            "max": round(float(np.max(valid)), 6),
            "std": round(float(np.std(valid)), 6),
            "var": round(float(np.var(valid)), 8),
            "count": int(len(valid)),
        })

    return {
        "stats": stats_list,
        "channel_count": len(stats_list),
        "data_rows": data.shape[0],
    }


# ---------------------------------------------------------------------------
# 降采样
# ---------------------------------------------------------------------------
def downsample(x, y, max_points=MAX_POINTS):
    n = len(x)
    if n <= max_points:
        return x, y
    idx = np.linspace(0, n - 1, max_points, dtype=int)
    return x[idx], y[idx]


# ---------------------------------------------------------------------------
# 单一压力-时间曲线图
# ---------------------------------------------------------------------------
def build_pressure_curve(filename: str, time_col: int, value_cols: list):
    """
    构建压力-时间曲线图

    filename   : data/ 目录下的文件名
    time_col   : Time 列的索引
    value_cols : 要绘制的列索引列表
    """
    filepath = DATA_DIR / filename
    if not filepath.exists():
        raise FileNotFoundError(f"文件 {filename} 不存在")

    headers, data = _read_file(filepath)

    # 时间向量
    time_raw = data[:, time_col]
    time_valid = ~np.isnan(time_raw)
    time_arr = time_raw[time_valid]

    # 颜色循环
    colors = [
        "#3b82f6", "#ef4444", "#22c55e", "#f59e0b", "#8b5cf6",
        "#06b6d4", "#ec4899", "#84cc16", "#f97316", "#6366f1",
    ]

    fig = go.Figure()

    for idx, col_idx in enumerate(value_cols):
        if col_idx < 0 or col_idx >= len(headers):
            continue

        # 提取标签：从 header 中取「流道XX」
        label = re.search(r"流道\d+(?:\.\d+)?", headers[col_idx])
        label = label.group() if label else headers[col_idx]

        color = colors[idx % len(colors)]

        # 取有效时间范围内的压力值，加 0.101325 大气压修正
        y_full = data[:, col_idx] + 0.101325
        y_arr = y_full[time_valid]
        # 过滤 NaN
        mask = ~np.isnan(y_arr)
        if np.sum(mask) < 2:
            continue

        x_ds, y_ds = downsample(time_arr[mask], y_arr[mask])

        fig.add_trace(go.Scatter(
            x=x_ds, y=y_ds, name=label,
            line=dict(color=color, width=2),
            mode="lines",
            hovertemplate=(
                f"t=%{{x:.4f}}s<br>p=%{{y:.4f}} MPa"
                + f"<extra>{label}</extra>"
            ),
        ))

    # 布局
    fig.update_xaxes(title_text="Time (s)")
    fig.update_yaxes(title_text="p (MPa)")

    fig.update_layout(
        template="plotly_white",
        height=500,
        margin=dict(l=60, r=30, t=30, b=50),
        legend=dict(
            orientation="h", yanchor="bottom", y=1.02,
            xanchor="center", x=0.5, font=dict(size=11),
        ),
        hovermode="x unified",
        dragmode="zoom",
    )

    return fig
