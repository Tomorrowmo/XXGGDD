"""
算例文件导入：校验名称与扩展名，写入项目 Case/ 目录（仅本机，无 SSH）。
case_root 通常为 <项目根>/Case，由 http_api 传入。
"""

from __future__ import annotations

import re
import threading
import uuid
from pathlib import Path
from typing import Callable

ProgressCallback = Callable[[float, str], None]

_ALLOWED_SUFFIXES = (".cas.h5", ".dat.h5")

_jobs_lock = threading.Lock()
_upload_jobs: dict[str, dict] = {}


def validate_case_name(name: str) -> str:
    s = (name or "").strip()
    if not s or s in (".", "..") or "/" in s or "\\" in s:
        raise ValueError("算例名称无效：不能包含路径分隔符或 . / ..")
    if not re.match(r"^[\w\-.]+$", s, re.ASCII):
        raise ValueError("算例名称仅允许字母、数字、下划线、连字符与点")
    return s


def validate_upload_filename(filename: str) -> str:
    if not filename or "/" in filename or "\\" in filename:
        raise ValueError(f"非法文件名: {filename}")
    base = Path(filename).name
    lower = base.lower()
    if not any(lower.endswith(suf) for suf in _ALLOWED_SUFFIXES):
        raise ValueError(f"仅支持上传 .cas.h5 与 .dat.h5，当前: {base}")
    return base


def create_upload_job() -> str:
    job_id = str(uuid.uuid4())
    with _jobs_lock:
        _upload_jobs[job_id] = {
            "percent": 0.0,
            "message": "等待开始",
            "status": "pending",
            "error": None,
            "case_name": None,
            "files": [],
        }
    return job_id


def get_upload_job(job_id: str) -> dict | None:
    with _jobs_lock:
        job = _upload_jobs.get(job_id)
        return dict(job) if job else None


def _update_job(job_id: str, **kwargs) -> None:
    with _jobs_lock:
        if job_id in _upload_jobs:
            _upload_jobs[job_id].update(kwargs)


def _make_progress(job_id: str | None, outer: ProgressCallback | None) -> ProgressCallback:
    def cb(percent: float, message: str) -> None:
        if job_id:
            _update_job(job_id, percent=round(percent, 2), message=message)
        if outer:
            outer(percent, message)

    return cb


def _write_files(
    dest_dir: Path,
    files: list[tuple[str, bytes]],
    progress: ProgressCallback,
) -> list[str]:
    dest_dir.mkdir(parents=True, exist_ok=True)
    total = sum(len(b) for _, b in files) or 1
    done_bytes = 0
    saved: list[str] = []
    chunk = 1024 * 1024
    for fname, data in files:
        path = dest_dir / fname
        progress(done_bytes / total * 100, f"写入: {fname}")
        with open(path, "wb") as f:
            offset = 0
            n = len(data)
            while offset < n:
                end = min(offset + chunk, n)
                f.write(data[offset:end])
                done_bytes += end - offset
                offset = end
                progress(done_bytes / total * 100, f"写入: {fname}")
        saved.append(fname)
    return saved


def import_case_files(
    case_root: Path,
    case_name: str,
    files: list[tuple[str, bytes]],
    *,
    job_id: str | None = None,
    progress_callback: ProgressCallback | None = None,
) -> dict:
    """
    将文件写入 case_root/<case_name>/（即项目 Case/<算例名>/）。
    files: [(filename, content_bytes), ...]
    """
    if not files:
        raise ValueError("未选择任何文件")

    safe_name = validate_case_name(case_name)
    normalized: list[tuple[str, bytes]] = []
    for fname, data in files:
        normalized.append((validate_upload_filename(fname), data))

    progress = _make_progress(job_id, progress_callback)
    progress(0.0, "准备写入 Case 目录…")
    if job_id:
        _update_job(job_id, status="running", case_name=safe_name)

    dest_dir = (case_root / safe_name).resolve()

    try:
        saved = _write_files(dest_dir, normalized, progress)
        progress(100.0, "导入完成")
        result = {
            "case_name": safe_name,
            "case_dir": str(dest_dir),
            "files": saved,
        }
        if job_id:
            _update_job(
                job_id,
                status="done",
                percent=100.0,
                message="导入完成",
                files=saved,
                case_name=safe_name,
                case_dir=str(dest_dir),
            )
        return result
    except Exception as e:
        if job_id:
            _update_job(job_id, status="error", error=str(e), message=str(e))
        raise


def run_import_in_background(
    case_root: Path,
    case_name: str,
    files: list[tuple[str, bytes]],
    job_id: str,
) -> None:
    def _worker() -> None:
        try:
            import_case_files(case_root, case_name, files, job_id=job_id)
        except Exception:
            pass

    threading.Thread(target=_worker, daemon=True).start()
