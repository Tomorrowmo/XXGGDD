"""入库测试：解析 + 去重 + 稳态测量写入 + 工况对齐。"""
from app.services.ingest import ingest_file, detect_kind, sha256_file
from app.db.models import Case, Measurement, CaseKind
from sqlalchemy import select
from pathlib import Path


def test_detect_kind(tmp_path):
    txt = tmp_path / "a.txt"; txt.write_text("x", encoding="utf-8")
    assert detect_kind(txt) == CaseKind.EXPERIMENT
    assert detect_kind(Path("case.cas.h5")) == CaseKind.SIMULATION
    assert detect_kind(Path("x.zip")) is None


def test_ingest_experiment(db, exp_file):
    res = ingest_file(db, exp_file, unit_name="试车台", delivery_label="Q1")
    assert res["ok"] and not res["deduped"]
    assert res["kind"] == "experiment"
    assert res["parse_status"] == "parsed"
    # 稳态关键量应写成测量
    meas = db.execute(select(Measurement).where(Measurement.case_id == res["case_id"])).scalars().all()
    assert len(meas) >= 3
    assert all(m.source_kind == CaseKind.EXPERIMENT for m in meas)


def test_ingest_dedup(db, exp_file):
    r1 = ingest_file(db, exp_file, unit_name="试车台", delivery_label="Q1")
    r2 = ingest_file(db, exp_file, unit_name="试车台", delivery_label="Q1")
    assert r2["deduped"] is True
    assert r2["case_id"] == r1["case_id"]
    # 只应有一个 Case
    n = db.execute(select(Case)).scalars().all()
    assert len(n) == 1


def test_sha256_stable(exp_file):
    assert sha256_file(Path(exp_file)) == sha256_file(Path(exp_file))
