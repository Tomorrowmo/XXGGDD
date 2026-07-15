"""后台入库任务：把入库从 HTTP 连接解耦。

点「开始入库」→ 在后台守护线程跑，**关掉弹窗也不中断**；前端轮询任务进度。
支持单文件与批量目录，进度含 当前文件+各步骤 + 已完成文件日志。
"""
from __future__ import annotations

import copy
import threading
import uuid
from pathlib import Path

from app.db.database import SessionLocal
from app.services import ingest as ingest_svc

_LOCK = threading.Lock()
_JOBS: dict[str, dict] = {}
_MAX_JOBS = 30   # 只保留最近 N 个任务，防内存无限增长


def start_ingest(path: str, unit_name: str, delivery_label: str, batch: bool) -> str:
    jid = uuid.uuid4().hex[:12]
    job = {"id": jid, "status": "running", "batch": bool(batch), "path": path,
           "total": 0, "done": 0, "ok": 0, "current": None, "log": [], "reason": None}
    with _LOCK:
        _JOBS[jid] = job
        if len(_JOBS) > _MAX_JOBS:                       # 清理最老的已结束任务
            for k in list(_JOBS):
                if _JOBS[k]["status"] != "running" and len(_JOBS) > _MAX_JOBS:
                    _JOBS.pop(k, None)
    threading.Thread(target=_run, args=(jid, path, unit_name, delivery_label, batch),
                     name=f"ingest-{jid}", daemon=True).start()
    return jid


def get_job(jid: str) -> dict | None:
    with _LOCK:
        j = _JOBS.get(jid)
        return copy.deepcopy(j) if j else None


def list_jobs() -> list[dict]:
    """活动 + 最近任务的精简列表（不含逐文件日志）。"""
    with _LOCK:
        out = []
        for j in _JOBS.values():
            out.append({"id": j["id"], "status": j["status"], "batch": j["batch"],
                        "total": j["total"], "done": j["done"], "ok": j["ok"],
                        "current": (j["current"] or {}).get("name")})
        return out


def _mut(jid: str, fn) -> None:
    with _LOCK:
        j = _JOBS.get(jid)
        if j is not None:
            fn(j)


def _run(jid, path, unit_name, delivery_label, batch):
    s = SessionLocal()
    try:
        p = Path(path)
        if batch:
            if not p.is_dir():
                _mut(jid, lambda j: (j.update(status="error", reason="目录不存在")))
                return
            files = [f for f in sorted(p.rglob("*"))
                     if f.is_file() and ingest_svc.detect_kind(f) is not None]
            _mut(jid, lambda j: j.update(total=len(files)))
            for i, f in enumerate(files):
                _ingest_one(jid, s, f, i + 1, len(files), unit_name, delivery_label)
        else:
            _mut(jid, lambda j: j.update(total=1))
            _ingest_one(jid, s, p, 1, 1, unit_name, delivery_label)
        _mut(jid, lambda j: j.update(status="done", current=None))
    except Exception as e:  # noqa: BLE001
        msg = str(e)[:200]
        _mut(jid, lambda j: j.update(status="error", reason=msg, current=None))
    finally:
        s.close()


def _ingest_one(jid, s, path: Path, index, total, unit_name, delivery_label):
    _mut(jid, lambda j: j.update(
        current={"name": path.name, "index": index, "total": total, "steps": {}}))
    res: dict = {"ok": False}
    try:
        for kind_, payload in ingest_svc.ingest_steps(
                s, path, unit_name=unit_name, delivery_label=delivery_label, with_slices=True):
            if kind_ == "result":
                res = payload
            else:
                step, status, detail = payload["step"], payload["status"], payload.get("detail")
                _mut(jid, lambda j, st=step, sta=status, de=detail: (
                    j["current"]["steps"].update({st: {"status": sta, "detail": de}})
                    if j.get("current") else None))
    except Exception as e:  # noqa: BLE001
        res = {"ok": False, "reason": str(e)[:120]}
    entry = {"name": path.name, "ok": bool(res.get("ok")), "deduped": res.get("deduped"),
             "reason": res.get("reason"), "n_measurements": res.get("n_measurements")}
    _mut(jid, lambda j: (j.update(done=j["done"] + 1,
                                  ok=j["ok"] + (1 if entry["ok"] else 0)),
                         j["log"].append(entry)))
