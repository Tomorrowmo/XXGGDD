"""交互图表与统计路由：压力曲线、通道统计、通道列表。"""
import json
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from app.config import DATA_DIR

router = APIRouter()


# ---------------------------------------------------------------------------
# API：交互图表数据
# ---------------------------------------------------------------------------
@router.post("/api/chart/pressure-curve")
async def chart_pressure_curve(body: dict):
    """根据用户选择的数据文件 + 列索引，生成压力-时间曲线 Plotly JSON"""
    from app.core.plotter import build_pressure_curve

    filename = body.get("filename", "")
    time_col = body.get("time_col", 0)
    value_cols = body.get("value_cols", [])

    if not filename:
        return JSONResponse({"error": "缺少 filename 参数"}, status_code=400)
    if not value_cols:
        return JSONResponse({"error": "缺少 value_cols 参数"}, status_code=400)

    try:
        fig = build_pressure_curve(filename, time_col, value_cols)
        return JSONResponse(content=json.loads(fig.to_json()))
    except FileNotFoundError as e:
        return JSONResponse({"error": str(e)}, status_code=404)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@router.post("/api/stats/compute")
async def stats_compute(body: dict):
    """计算所有流道通道的统计值"""
    from app.core.plotter import compute_channel_stats

    filename = body.get("filename", "")
    if not filename:
        return JSONResponse({"error": "缺少 filename 参数"}, status_code=400)

    try:
        result = compute_channel_stats(filename)
        return JSONResponse(result)
    except FileNotFoundError as e:
        return JSONResponse({"error": str(e)}, status_code=404)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@router.get("/api/chart/channels")
async def chart_channels(filename: str):
    """获取文件中所有「流道」相关列的索引和标签"""
    from app.core.plotter import _read_file, extract_channels

    filepath = DATA_DIR / filename
    if not filepath.exists():
        return JSONResponse({"error": f"文件 {filename} 不存在"}, status_code=404)

    try:
        headers, _ = _read_file(filepath)
        channels = extract_channels(headers)
        time_cols = [i for i, h in enumerate(headers) if "time" in h.lower() or "Time" in h]
        return JSONResponse({
            "channels": channels,
            "time_cols": time_cols,
            "total_cols": len(headers),
        })
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)
