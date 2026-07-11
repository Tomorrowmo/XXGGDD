"""试验数据文件管理路由：上传/列表/删除/重命名 + data 信息。"""
import shutil
from fastapi import APIRouter, UploadFile, File
from fastapi.responses import JSONResponse
from app.config import ROOT, DATA_DIR

router = APIRouter()


# ---------------------------------------------------------------------------
# API：数据信息
# ---------------------------------------------------------------------------
@router.get("/api/data/info")
async def data_info(filename: str):
    """读取 data/ 目录下指定文件的 header 信息和基本统计"""
    from A00_parameterData import headerIndex

    file_path = ROOT / "data" / filename
    if not file_path.exists():
        return JSONResponse({"error": f"文件 {filename} 不存在"}, status_code=404)

    try:
        # 读取原始行
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()

        total_lines = len(lines)
        if total_lines <= headerIndex:
            return JSONResponse({"error": "文件行数不足，headerIndex 超出范围"}, status_code=400)

        # 解析 header
        header_line = lines[headerIndex].strip()
        headers = [h.strip() for h in header_line.split(",")]

        # 统计数据行
        data_rows = total_lines - headerIndex - 1

        # 采样前几行数据
        sample_rows = []
        for i in range(headerIndex + 1, min(headerIndex + 4, total_lines)):
            sample_rows.append(lines[i].strip())

        return JSONResponse({
            "filename": filename,
            "total_lines": total_lines,
            "header_index": headerIndex,
            "column_count": len(headers),
            "data_rows": data_rows,
            "headers": headers,
            "sample_rows": sample_rows,
            "size_bytes": file_path.stat().st_size,
        })
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@router.post("/api/upload")
async def upload_file(file: UploadFile = File(...)):
    """上传试验数据文件到 data/ 目录"""
    if not file.filename:
        return JSONResponse({"error": "文件名为空"}, status_code=400)

    data_dir = ROOT / "data"
    data_dir.mkdir(exist_ok=True)

    save_path = data_dir / file.filename
    with open(save_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    file_size = save_path.stat().st_size
    return JSONResponse({
        "filename": file.filename,
        "size_bytes": file_size,
        "message": f"文件 {file.filename} 上传成功",
    })


@router.get("/api/files")
async def list_files():
    """列出 data/ 目录下已上传的文件"""
    data_dir = ROOT / "data"
    if not data_dir.exists():
        return JSONResponse({"files": []})
    files = sorted(data_dir.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True)
    return JSONResponse({
        "files": [{"name": f.name, "size_bytes": f.stat().st_size} for f in files if f.is_file()]
    })


@router.delete("/api/files/{filename}")
async def delete_file(filename: str):
    """删除 data/ 目录下的文件"""
    file_path = ROOT / "data" / filename
    if not file_path.exists():
        return JSONResponse({"error": "文件不存在"}, status_code=404)
    try:
        file_path.unlink()
        return JSONResponse({"message": f"文件 {filename} 已删除"})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@router.put("/api/files/{filename}/rename")
async def rename_file(filename: str, body: dict):
    """重命名 data/ 目录下的文件"""
    new_name = body.get("new_name", "").strip()
    if not new_name:
        return JSONResponse({"error": "新文件名不能为空"}, status_code=400)
    old_path = ROOT / "data" / filename
    new_path = ROOT / "data" / new_name
    if not old_path.exists():
        return JSONResponse({"error": "文件不存在"}, status_code=404)
    if new_path.exists():
        return JSONResponse({"error": "目标文件名已存在"}, status_code=409)
    try:
        old_path.rename(new_path)
        return JSONResponse({"message": f"{filename} → {new_name} 重命名成功"})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)
