"""批量入库服务 —— 对齐原型「数据资源库·批量入库」与 SimGraph2 两阶段入库骨架。

流程：扫描 → 识别类型 → SHA-256 去重 → 解析（simparse / 试验解析）→ 工况对齐 →
写 Unit/Delivery/Case/Measurement。仿真侧的四切片快照走后台（viz），此处只登记。
"""
from __future__ import annotations

import hashlib
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import (
    Unit, Delivery, Case, Measurement, Quantity, OperatingPoint,
    CaseKind, ParseStatus, Confidence,
)
from app.services import simparse_adapter, operating_point as op_svc
from app.services import experiment as exp_svc
from app.services import viz


# 注意：Fluent 传统二进制 .cas/.dat（非 HDF5）不受支持——需在 Fluent 导出为 .cas.h5/.dat.h5 或 .cgns
SIM_EXTS = {".h5", ".foam", ".cgns"}
EXP_EXTS = {".txt", ".csv"}


def sha256_file(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while blk := f.read(chunk):
            h.update(blk)
    return h.hexdigest()


def _is_openfoam_dir(path: Path) -> bool:
    return (path / "system" / "controlDict").exists() or bool(list(path.glob("*.foam")))


def _sim_file_in_dir(path: Path) -> Path | None:
    """目录内的主仿真文件：CGNS 优先，其次 Fluent HDF5(.cas.h5)。找不到返回 None。"""
    cgns = sorted(path.glob("*.cgns"))
    if cgns:
        return cgns[0]
    cas = sorted(path.glob("*.cas.h5"))
    dat = sorted(path.glob("*.dat.h5"))
    if cas and dat:
        return cas[0]
    return None


def detect_kind(path: Path) -> CaseKind | None:
    if path.is_dir():
        if _is_openfoam_dir(path):                 # OpenFOAM 算例目录
            return CaseKind.SIMULATION
        if _sim_file_in_dir(path) is not None:     # 目录内含 CGNS / Fluent HDF5
            return CaseKind.SIMULATION
        return None
    ext = path.suffix.lower()
    if ext in EXP_EXTS:
        return CaseKind.EXPERIMENT
    if ext in SIM_EXTS or path.name.endswith((".cas.h5", ".dat.h5")):
        return CaseKind.SIMULATION
    return None


def resolve_case_path(path: Path) -> Path:
    """把仿真"目录"解析到实际可解析对象：OpenFOAM 用目录本身；含 CGNS/Fluent HDF5 的目录 → 该文件。"""
    if path.is_dir() and not _is_openfoam_dir(path):
        f = _sim_file_in_dir(path)
        if f is not None:
            return f
    return path


_SUPPORTED_HINT = ("支持格式：OpenFOAM 目录(含 system/controlDict)、CGNS(.cgns)、"
                   "Fluent HDF5(.cas.h5 + .dat.h5)、试验数据(.txt/.csv)")


def unsupported_reason(path: Path) -> str:
    """给出"为什么不支持"的具体说明——列出目录内实际扩展名 + 支持清单 + Fluent 传统格式提示。"""
    if path.is_dir():
        exts = sorted({p.suffix.lower() for p in path.iterdir() if p.is_file()})
        has_legacy = any(e in (".cas", ".dat") for e in exts)
        subdirs = [p.name for p in path.iterdir() if p.is_dir()]
        detail = f"目录直接包含文件类型：{', '.join(exts) if exts else '（无文件，仅子目录：' + ', '.join(subdirs[:5]) + '）'}"
        tips = []
        if has_legacy:
            tips.append("检测到 Fluent 传统 .cas/.dat（二进制，非 HDF5）——请在 Fluent 里 File→Export 导出为 .cas.h5/.dat.h5 或 .cgns")
        if subdirs and not exts:
            tips.append("看起来是含子目录的父目录——若里面是多个算例，请勾选『批量目录扫描』；若是单个算例，请把路径指到含算例文件的子目录")
        return f"未识别为可入库算例。{detail}。{_SUPPORTED_HINT}。" + ("；".join(tips) and ("提示：" + "；".join(tips)))
    ext = path.suffix.lower() or "（无扩展名）"
    tip = ""
    if ext in (".cas", ".dat"):
        tip = "。Fluent 传统 .cas/.dat 为二进制格式不支持，请导出为 .cas.h5/.dat.h5 或 .cgns"
    return f"文件类型 {ext} 不支持。{_SUPPORTED_HINT}{tip}"


def _content_hash(path: Path) -> str:
    """文件哈希其内容；OpenFOAM 目录哈希 controlDict（无则路径）。"""
    if path.is_dir():
        cd = path / "system" / "controlDict"
        if cd.exists():
            return sha256_file(cd)
        h = hashlib.sha256(); h.update(str(path.resolve()).encode()); return h.hexdigest()
    return sha256_file(path)


def _get_or_create_unit(db: Session, name: str) -> Unit:
    u = db.execute(select(Unit).where(Unit.name == name)).scalar_one_or_none()
    if u is None:
        u = Unit(name=name, type="试车台" if "试车" in name else "承研单位")
        db.add(u); db.flush()
    return u


def _get_or_create_delivery(db: Session, unit: Unit, label: str) -> Delivery:
    d = db.execute(
        select(Delivery).where(Delivery.unit_id == unit.id, Delivery.label == label)
    ).scalar_one_or_none()
    if d is None:
        d = Delivery(unit_id=unit.id, label=label)
        db.add(d); db.flush()
    return d


def _get_or_create_quantity(db: Session, key: str, name: str, unit_dim: str) -> Quantity:
    q = db.execute(select(Quantity).where(Quantity.key == key)).scalar_one_or_none()
    if q is None:
        q = Quantity(key=key, physical_name=name, standard_unit=unit_dim)
        db.add(q); db.flush()
    return q


def ingest_file(db: Session, path: str | Path, *, unit_name: str,
                delivery_label: str, note: str | None = None) -> dict:
    """入库单个文件（幂等：content_hash 去重）。返回入库结果。"""
    result: dict = {"ok": False, "reason": "未知"}
    for kind_, payload in ingest_steps(db, path, unit_name=unit_name,
                                       delivery_label=delivery_label, with_slices=False):
        if kind_ == "result":
            result = payload
    return result


# 入库步骤事件流：yields ("step", {...}) 供进度展示，最后 yields ("result", {...})。
# 同一套逻辑既供同步 ingest_file，又供流式端点（见 routers/library）。
def ingest_steps(db: Session, path: str | Path, *, unit_name: str,
                 delivery_label: str, with_slices: bool = False):
    def step(key, status, detail=None):
        ev = {"step": key, "status": status}
        if detail is not None:
            ev["detail"] = detail
        return ("step", ev)

    path = Path(path)
    if not path.exists():
        yield ("result", {"ok": False, "reason": "文件不存在", "path": str(path)})
        return

    yield step("detect", "run", "识别数据类型")
    kind = detect_kind(path)
    if kind is None:
        reason = unsupported_reason(path)
        yield step("detect", "fail", reason)
        yield ("result", {"ok": False, "reason": reason, "path": str(path)})
        return
    # 仿真"目录"解析到实际文件（含 CGNS / Fluent HDF5 的文件夹 → 该文件；OpenFOAM 仍用目录）
    src_name = path.name if path.is_dir() else path.stem
    if kind == CaseKind.SIMULATION:
        resolved = resolve_case_path(path)
        if resolved != path:
            src_name = resolved.stem
        path = resolved
    is_of = path.is_dir()
    sfmt = ("openfoam" if is_of else
            ("cgns" if path.suffix.lower() == ".cgns" else "fluent-hdf5")) \
        if kind == CaseKind.SIMULATION else "txt-experiment"
    kind_txt = ("仿真算例 · " + sfmt) if kind == CaseKind.SIMULATION else "试验数据 · txt/csv"
    yield step("detect", "ok", kind_txt)

    yield step("dedup", "run", "SHA-256 去重")
    chash = _content_hash(path)
    dup = db.execute(select(Case).where(Case.content_hash == chash)).scalar_one_or_none()
    if dup is not None:
        yield step("dedup", "ok", "已存在，去重跳过")
        yield ("result", {"ok": True, "deduped": True, "case_id": dup.id, "name": dup.name})
        return
    yield step("dedup", "ok", "新数据")

    unit = _get_or_create_unit(db, unit_name)
    delivery = _get_or_create_delivery(db, unit, delivery_label)
    case = Case(
        delivery_id=delivery.id, kind=kind, name=src_name,
        source_format=sfmt, storage_uri=str(path.resolve()), content_hash=chash,
        parse_status=ParseStatus.PENDING, parse_confidence=Confidence.PENDING,
    )
    db.add(case); db.flush()

    yield step("parse", "run", "解析 + 提取关键量")
    op_params: dict | None = None
    n_meas = 0
    try:
        if kind == CaseKind.SIMULATION:
            summ = simparse_adapter.summary(str(path))
            case.context = summ.get("summary") if summ.get("available") else None
            case.parse_status = ParseStatus.PARSED if summ.get("available") else ParseStatus.FAILED
            case.parse_confidence = Confidence.HIGH if summ.get("available") else Confidence.PENDING
            op_params = (case.context or {}).get("operating_point") if case.context else None
            qres = simparse_adapter.qoi(str(path))
            if qres.get("available"):
                n_meas = _write_sim_measurements(db, case, qres.get("qoi") or [])
            yield step("parse", "ok" if summ.get("available") else "fail",
                       f"simparse · {n_meas} 项 QOI")
        else:
            parsed = exp_svc.read_experiment(path)
            phases = exp_svc.segment_phases(parsed)
            steady = exp_svc.extract_steady_qoi(parsed, phases)
            case.context = {"n_rows": parsed.n_rows, "channels": len(parsed.channels)}
            case.parse_status = ParseStatus.PARSED
            case.parse_confidence = Confidence.HIGH
            n_meas = _write_experiment_measurements(db, case, steady)
            yield step("parse", "ok", f"{len(parsed.channels)} 通道 · {n_meas} 稳态关键量")
    except Exception as e:  # noqa: BLE001
        case.parse_status = ParseStatus.FAILED
        case.context = {"error": str(e)}
        yield step("parse", "fail", str(e)[:80])

    yield step("align", "run", "工况对齐")
    link = op_svc.align_case(db, case, op_params)
    db.commit()
    op_key = None
    if link.op_id:
        op = db.get(OperatingPoint, link.op_id)
        op_key = op.canonical_key if op else None
    conf = link.mapping_confidence.value
    yield step("align", "ok",
               (op_key if op_key and op_key != "__UNALIGNED__" else "待人工对齐") + f" · {conf}")

    yield step("write", "ok", f"写入 {n_meas} 条测量")

    if with_slices and kind == CaseKind.SIMULATION:
        yield step("slice", "run", "生成多方向切片")
        try:
            pv = viz.generate_previews(str(path))
            if pv.get("available"):
                yield step("slice", "ok", f"{len(pv.get('images', {}))} 图 · {pv.get('engine', '')}")
            else:
                yield step("slice", "skip", pv.get("reason", "该格式暂不支持渲染"))
        except Exception as e:  # noqa: BLE001
            yield step("slice", "skip", str(e)[:80])

    yield ("result", {"ok": True, "deduped": False, "case_id": case.id, "name": case.name,
                      "kind": kind.value, "parse_status": case.parse_status.value,
                      "n_measurements": n_meas, "operating_point": op_key,
                      "op_link": {"method": link.method.value, "confidence": conf}})


def _write_sim_measurements(db: Session, case: Case, qoi_list: list) -> int:
    """把 simparse QOI 写成仿真测量（防御式，兼容 dict/对象、多种字段名）。返回写入条数。"""
    n = 0
    for item in qoi_list:
        def g(*keys, default=None):
            for k in keys:
                if isinstance(item, dict) and k in item:
                    return item[k]
                v = getattr(item, k, None)
                if v is not None:
                    return v
            return default
        name = g("variable", "name", "quantity", "key")
        value = g("value", "val")
        unit = g("unit", "units", default="")
        # 跳过布尔/非数值判据量（如 is_extinguished），只留可比物理量
        if name is None or value is None or isinstance(value, bool) or str(unit).lower() == "boolean":
            continue
        try:
            value = float(value)
        except (TypeError, ValueError):
            continue
        conf_raw = str(g("confidence", default="MED")).upper()
        conf = Confidence[conf_raw] if conf_raw in Confidence.__members__ else Confidence.MED
        q = _get_or_create_quantity(db, key=str(name), name=str(name), unit_dim=str(unit))
        db.add(Measurement(
            case_id=case.id, op_id=None, quantity_id=q.id, value=value, unit=str(unit),
            raw_name=str(name), source_kind=CaseKind.SIMULATION, status="normal",
            confidence=conf, evidence={"source": "simparse.qoi",
                                       "reference": g("reference", "evidence")},
        ))
        n += 1
    db.flush()
    return n


def _write_experiment_measurements(db: Session, case: Case, steady_qoi: list[dict]) -> int:
    """把试验稳态关键量写成 Measurement（实验真值来源）。返回写入条数。"""
    n = 0
    for item in steady_qoi:
        q = _get_or_create_quantity(db, key=item["channel"], name=item["quantity"],
                                    unit_dim=item["unit"])
        db.add(Measurement(
            case_id=case.id, op_id=None, quantity_id=q.id,
            value=item["value"], unit=item["unit"], raw_name=item["channel"],
            source_kind=CaseKind.EXPERIMENT, status="normal",
            confidence=Confidence.HIGH,
            evidence={"method": item["method"], "category": item.get("category")},
        ))
        n += 1
    db.flush()
    return n


def ingest_directory(db: Session, directory: str | Path, *, unit_name: str,
                     delivery_label: str) -> dict:
    """入库整个目录（批量）。"""
    directory = Path(directory)
    results = []
    for p in sorted(directory.rglob("*")):
        if p.is_file() and detect_kind(p) is not None:
            results.append(ingest_file(db, p, unit_name=unit_name, delivery_label=delivery_label))
    ok = sum(1 for r in results if r.get("ok"))
    return {"total": len(results), "ok": ok, "results": results}
