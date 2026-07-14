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
    Unit, Delivery, Case, Measurement, Quantity,
    CaseKind, ParseStatus, Confidence,
)
from app.services import simparse_adapter, operating_point as op_svc
from app.services import experiment as exp_svc


SIM_EXTS = {".h5", ".cas", ".dat", ".foam", ".cgns"}
EXP_EXTS = {".txt", ".csv"}


def sha256_file(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while blk := f.read(chunk):
            h.update(blk)
    return h.hexdigest()


def detect_kind(path: Path) -> CaseKind | None:
    if path.is_dir():
        # OpenFOAM 算例目录：含 system/controlDict 或 *.foam
        if (path / "system" / "controlDict").exists() or any(path.glob("*.foam")):
            return CaseKind.SIMULATION
        return None
    ext = path.suffix.lower()
    if ext in EXP_EXTS:
        return CaseKind.EXPERIMENT
    if ext in SIM_EXTS or path.name.endswith((".cas.h5", ".dat.h5")):
        return CaseKind.SIMULATION
    return None


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
    path = Path(path)
    if not path.exists():
        return {"ok": False, "reason": "文件不存在", "path": str(path)}
    kind = detect_kind(path)
    if kind is None:
        return {"ok": False, "reason": "不支持的类型", "path": str(path)}

    chash = _content_hash(path)
    dup = db.execute(select(Case).where(Case.content_hash == chash)).scalar_one_or_none()
    if dup is not None:
        return {"ok": True, "deduped": True, "case_id": dup.id, "name": dup.name}

    unit = _get_or_create_unit(db, unit_name)
    delivery = _get_or_create_delivery(db, unit, delivery_label)

    if kind == CaseKind.SIMULATION:
        sfmt = "openfoam" if path.is_dir() else "fluent-hdf5"
    else:
        sfmt = "txt-experiment"
    case = Case(
        delivery_id=delivery.id, kind=kind, name=path.name if path.is_dir() else path.stem,
        source_format=sfmt,
        storage_uri=str(path.resolve()), content_hash=chash,
        parse_status=ParseStatus.PENDING, parse_confidence=Confidence.PENDING,
    )
    db.add(case); db.flush()

    # 解析 + 工况对齐 + 关键量
    op_params: dict | None = None
    try:
        if kind == CaseKind.SIMULATION:
            summ = simparse_adapter.summary(str(path))
            case.context = summ.get("summary") if summ.get("available") else None
            case.parse_status = ParseStatus.PARSED if summ.get("available") else ParseStatus.FAILED
            case.parse_confidence = Confidence.HIGH if summ.get("available") else Confidence.PENDING
            op_params = (case.context or {}).get("operating_point") if case.context else None
            # 仿真 QOI → 测量（供对比评估）
            qres = simparse_adapter.qoi(str(path))
            if qres.get("available"):
                _write_sim_measurements(db, case, qres.get("qoi") or [])
        else:
            parsed = exp_svc.read_experiment(path)
            phases = exp_svc.segment_phases(parsed)
            steady = exp_svc.extract_steady_qoi(parsed, phases)
            case.context = {"n_rows": parsed.n_rows, "channels": len(parsed.channels)}
            case.parse_status = ParseStatus.PARSED
            case.parse_confidence = Confidence.HIGH
            _write_experiment_measurements(db, case, steady)
    except Exception as e:  # noqa: BLE001
        case.parse_status = ParseStatus.FAILED
        case.context = {"error": str(e)}

    link = op_svc.align_case(db, case, op_params)
    db.commit()
    return {"ok": True, "deduped": False, "case_id": case.id, "name": case.name,
            "kind": kind.value, "parse_status": case.parse_status.value,
            "op_link": {"method": link.method.value,
                        "confidence": link.mapping_confidence.value}}


def _write_sim_measurements(db: Session, case: Case, qoi_list: list) -> None:
    """把 simparse QOI 写成仿真测量（防御式，兼容 dict/对象、多种字段名）。"""
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
    db.flush()


def _write_experiment_measurements(db: Session, case: Case, steady_qoi: list[dict]) -> None:
    """把试验稳态关键量写成 Measurement（实验真值来源）。"""
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
    db.flush()


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
